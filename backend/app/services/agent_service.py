"""Agent 服务 - Agent CRUD + 聊天入口

设计要点：
1. 多租户隔离：所有查询都带 business_id
2. 每个商户默认只能有一个 active Agent（uk_agents_business_id 部分索引）
3. 新建 Agent 自动 status=ready（跳过 initializing）
4. allowed_tools 存在 config JSONB 中（避免新增字段）
"""
import json
import logging
from typing import Optional, Tuple

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.executor import get_executor
from app.agent.llm import get_default_model_name
from app.agent.types import AgentConfig, AgentResponse
from app.models.agent import Agent, AgentSession, AgentMessage
from app.schemas.agent import AgentCreate, AgentUpdate
from app.agent.tools.builtin import DEFAULT_ALLOWED_TOOLS

logger = logging.getLogger(__name__)


# ===== 内部辅助 =====

def _agent_dict(agent: Agent) -> dict:
    """Agent 序列化为 dict"""
    config = agent.config or {}
    allowed_tools = config.get("allowed_tools") if isinstance(config, dict) else None
    if not allowed_tools:
        allowed_tools = DEFAULT_ALLOWED_TOOLS
    return {
        "id": agent.id,
        "business_id": agent.business_id,
        "name": agent.name,
        "role": agent.role,
        "avatar": agent.avatar,
        "autonomy_level": agent.autonomy_level,
        "status": agent.status,
        "model": agent.model,
        "system_prompt_text": agent.system_prompt_text,
        "config": config,
        "allowed_tools": allowed_tools,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
    }


def _session_dict(sess: AgentSession) -> dict:
    return {
        "id": sess.id,
        "agent_id": sess.agent_id,
        "session_type": sess.session_type,
        "title": sess.title,
        "status": sess.status,
        "context_summary": sess.context_summary,
        "closed_at": sess.closed_at.isoformat() if sess.closed_at else None,
        "created_at": sess.created_at.isoformat() if sess.created_at else None,
        "updated_at": sess.updated_at.isoformat() if sess.updated_at else None,
    }


def _message_dict(m: AgentMessage) -> dict:
    return {
        "id": m.id,
        "session_id": m.session_id,
        "role": m.role,
        "content": m.content,
        "tool_calls": m.tool_calls,
        "tool_call_id": m.tool_call_id,
        "tool_name": m.tool_name,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


async def _get_agent_by_id(db: AsyncSession, business_id: int, agent_id: int) -> Optional[Agent]:
    """按 id 查询 Agent（带 business_id 校验）"""
    stmt = select(Agent).where(
        Agent.id == agent_id,
        Agent.business_id == business_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ===== CRUD =====

async def create_agent(
    db: AsyncSession, business_id: int, req: AgentCreate
) -> Agent:
    """创建 Agent"""
    # 把 allowed_tools 存到 config 中
    config = req.config or {}
    if isinstance(config, dict):
        config = dict(config)
    else:
        config = {}
    config["allowed_tools"] = req.allowed_tools

    agent = Agent(
        business_id=business_id,
        name=req.name,
        role=req.role,
        avatar=req.avatar,
        autonomy_level=req.autonomy_level,
        status="ready",  # 直接就绪
        model=req.model,
        system_prompt_text=req.system_prompt_text,
        config=config,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    logger.info(f"[AgentService] 创建 Agent {agent.id}（business={business_id}）")
    return agent


async def list_agents(
    db: AsyncSession,
    business_id: int,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[list, int]:
    """查询 Agent 列表"""
    stmt = select(Agent).where(Agent.business_id == business_id)
    if status:
        stmt = stmt.where(Agent.status == status)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(Agent.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = [_agent_dict(a) for a in result.scalars().all()]
    return items, total


async def get_agent(
    db: AsyncSession, business_id: int, agent_id: int
) -> Optional[Agent]:
    """获取 Agent 详情"""
    return await _get_agent_by_id(db, business_id, agent_id)


async def update_agent(
    db: AsyncSession, business_id: int, agent_id: int, req: AgentUpdate
) -> Optional[Agent]:
    """更新 Agent"""
    agent = await _get_agent_by_id(db, business_id, agent_id)
    if agent is None:
        return None

    if req.name is not None:
        agent.name = req.name
    if req.avatar is not None:
        agent.avatar = req.avatar
    if req.autonomy_level is not None:
        agent.autonomy_level = req.autonomy_level
    if req.status is not None:
        agent.status = req.status
    if req.model is not None:
        agent.model = req.model
    if req.system_prompt_text is not None:
        agent.system_prompt_text = req.system_prompt_text
    if req.config is not None or req.allowed_tools is not None:
        config = dict(agent.config or {})
        if req.config is not None:
            config.update(req.config)
        if req.allowed_tools is not None:
            config["allowed_tools"] = req.allowed_tools
        agent.config = config

    await db.commit()
    await db.refresh(agent)
    return agent


async def delete_agent(
    db: AsyncSession, business_id: int, agent_id: int
) -> Optional[Agent]:
    """停用 Agent（status=stopped，不软删）"""
    agent = await _get_agent_by_id(db, business_id, agent_id)
    if agent is None:
        return None
    agent.status = "stopped"
    await db.commit()
    await db.refresh(agent)
    return agent


# ===== 会话管理 =====

async def list_sessions(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[list, int]:
    """查询某个 Agent 的会话列表"""
    # 先校验 Agent 归属
    agent = await _get_agent_by_id(db, business_id, agent_id)
    if agent is None:
        return [], 0

    stmt = select(AgentSession).where(
        AgentSession.agent_id == agent_id,
        AgentSession.business_id == business_id,
    )
    if status:
        stmt = stmt.where(AgentSession.status == status)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(AgentSession.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = [_session_dict(s) for s in result.scalars().all()]
    return items, total


async def list_messages(
    db: AsyncSession,
    business_id: int,
    session_id: int,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[list, int]:
    """查询会话消息历史"""
    # 校验会话归属
    sess_stmt = select(AgentSession).where(
        AgentSession.id == session_id,
        AgentSession.business_id == business_id,
    )
    sess = (await db.execute(sess_stmt)).scalar_one_or_none()
    if sess is None:
        return [], 0

    stmt = select(AgentMessage).where(AgentMessage.session_id == session_id)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(AgentMessage.created_at.asc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = [_message_dict(m) for m in result.scalars().all()]
    return items, total


async def create_session(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    title: Optional[str] = None,
    session_type: str = "chat",
) -> Optional[AgentSession]:
    """创建空会话（不发送消息，供前端预创建会话）"""
    agent = await _get_agent_by_id(db, business_id, agent_id)
    if agent is None:
        return None
    if agent.status not in ("ready", "running"):
        raise ValueError(f"Agent 当前状态为 {agent.status}，无法创建会话")

    sess = AgentSession(
        agent_id=agent_id,
        business_id=business_id,
        session_type=session_type,
        title=title or "新会话",
        status="active",
    )
    db.add(sess)
    await db.commit()
    await db.refresh(sess)
    logger.info(f"[AgentService] 创建会话 {sess.id}（agent={agent_id}）")
    return sess


async def close_session(
    db: AsyncSession,
    business_id: int,
    session_id: int,
) -> Optional[AgentSession]:
    """关闭会话（status=closed）"""
    stmt = select(AgentSession).where(
        AgentSession.id == session_id,
        AgentSession.business_id == business_id,
    )
    sess = (await db.execute(stmt)).scalar_one_or_none()
    if sess is None:
        return None
    sess.status = "closed"
    from app.agent.types import utcnow_naive
    sess.closed_at = utcnow_naive()
    await db.commit()
    await db.refresh(sess)
    logger.info(f"[AgentService] 关闭会话 {sess.id}")
    return sess


# ===== 聊天入口 =====

async def chat_with_agent(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    message: str,
    session_id: Optional[int] = None,
) -> AgentResponse:
    """与 Agent 聊天 - 非流式"""
    agent = await _get_agent_by_id(db, business_id, agent_id)
    if agent is None:
        raise ValueError("Agent 不存在")
    if agent.status not in ("ready", "running"):
        raise ValueError(f"Agent 当前状态为 {agent.status}，无法聊天")

    # 构造 AgentConfig
    config_dict = agent.config or {}
    allowed_tools = config_dict.get("allowed_tools") if isinstance(config_dict, dict) else None
    if not allowed_tools:
        allowed_tools = DEFAULT_ALLOWED_TOOLS

    agent_config = AgentConfig(
        agent_id=agent.id,
        business_id=agent.business_id,
        name=agent.name,
        role=agent.role,
        model=agent.model or get_default_model_name(),
        autonomy_level=agent.autonomy_level,
        system_prompt_text=agent.system_prompt_text,
        config=config_dict if isinstance(config_dict, dict) else {},
        allowed_tools=allowed_tools,
    )

    # 调用执行器
    executor = get_executor()
    response = await executor.run(
        db=db,
        agent_config=agent_config,
        user_message=message,
        session_id=session_id,
        stream_callback=None,
    )
    return response


async def chat_with_agent_stream(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    message: str,
    session_id: Optional[int] = None,
):
    """与 Agent 聊天 - SSE 流式生成器

    yield 出 (event_type, data) 元组，由 API 层包装成 SSE。
    """
    agent = await _get_agent_by_id(db, business_id, agent_id)
    if agent is None:
        yield ("error", "Agent 不存在")
        return
    if agent.status not in ("ready", "running"):
        yield ("error", f"Agent 当前状态为 {agent.status}，无法聊天")
        return

    config_dict = agent.config or {}
    allowed_tools = config_dict.get("allowed_tools") if isinstance(config_dict, dict) else None
    if not allowed_tools:
        allowed_tools = DEFAULT_ALLOWED_TOOLS

    agent_config = AgentConfig(
        agent_id=agent.id,
        business_id=agent.business_id,
        name=agent.name,
        role=agent.role,
        model=agent.model or get_default_model_name(),
        autonomy_level=agent.autonomy_level,
        system_prompt_text=agent.system_prompt_text,
        config=config_dict if isinstance(config_dict, dict) else {},
        allowed_tools=allowed_tools,
    )

    # 异步队列收集流式事件
    import asyncio
    queue: asyncio.Queue = asyncio.Queue()

    async def stream_callback(event_type: str, data: str):
        await queue.put((event_type, data))

    executor = get_executor()

    # 启动执行任务
    async def run_task():
        try:
            response = await executor.run(
                db=db,
                agent_config=agent_config,
                user_message=message,
                session_id=session_id,
                stream_callback=stream_callback,
            )
            # 标记完成
            await queue.put(("final", response))
        except Exception as e:
            logger.error(f"[chat_stream] 执行异常：{e}", exc_info=True)
            await queue.put(("error", str(e)))

    task = asyncio.create_task(run_task())

    # 流式吐出
    try:
        while True:
            event_type, data = await queue.get()
            if event_type == "final":
                # AgentResponse 对象，构造完整 done 事件
                resp = data
                import json as _json
                done_data = _json.dumps({
                    "session_id": resp.session_id,
                    "status": resp.status,
                    "message": resp.message,
                    "loop_count": resp.loop_count,
                    "tool_call_count": resp.tool_call_count,
                    "pending_approvals": len(resp.approval_work_order_ids),
                    "approval_work_order_ids": resp.approval_work_order_ids,
                    "token_usage": {
                        "input": resp.token_usage.input,
                        "output": resp.token_usage.output,
                    },
                }, ensure_ascii=False)
                yield ("done", done_data)
                break
            if event_type == "error":
                yield ("error", data)
                break
            # metadata 事件忽略（信息已包含在 final 中）
            if event_type == "metadata":
                continue
            yield (event_type, data)
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
