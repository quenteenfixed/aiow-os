"""Agent 执行器 - 8 步 ReAct 循环（M2-3 升级版）

完整 8 步：
1. 接收消息（Receive）- 创建/恢复会话
2. 构造提示词（Build Prompt）- system + messages + tools
3. 调用 LLM（Call LLM）- Mock 或真实 Anthropic
4. 解析工具调用（Parse Tool Calls）
5. 门禁检查（Gate Check）- M2-3 升级为 5 道门禁 Pipeline
6. 执行工具（Execute Tool）- 服务端身份注入
7. 结果写回（Write Back）- 持久化 tool_result 到 DB
8. 循环控制（Loop Control）- 有 tool_use 继续，否则终止

M2-3 变更（相对 M2-1）：
- 门禁从 2 道（Fencing + RateLimit）升级为 5 道 Pipeline
- 新增 pending_approval 状态：高风险写入操作进入审批流程
- read_set 由 ToolExecutor.extract_object_ids 维护，供 Provenance Gate 校验

简化点（相对完整版）：
- 记忆系统留 M4-1，本阶段不实现
- 审批工单创建留 M3-1（Approval Gate scaffold 占位）
- 流式：通过 stream_callback 回调推送文本片段
"""
import json
import logging
from typing import Awaitable, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import LLMClient, LLMError
from app.agent.session import SessionManager
from app.agent.tools.executor import ToolExecutor
from app.agent.tools.parser import ToolCallParser
from app.agent.tools.registry import ToolRegistry, ToolNotFoundError
from app.agent.gates import get_gate_pipeline, GatePipeline
from app.agent.types import (
    AgentConfig, AgentResponse, SessionContext, ToolCall, ToolResult,
)
from app.services.memory_service import search_memories, create_memory

logger = logging.getLogger(__name__)


# 默认系统提示词
DEFAULT_SYSTEM_PROMPT = """你是 {business_name} 的门店管家 AI 助手，名字叫 {agent_name}。

## 角色定位
你是门店的数字化管理者，帮助店主管理商品、库存、订单、客户等业务。

## 行为准则
1. 接到用户查询后，先用工具查询数据，再基于结果回答
2. 工具结果中已包含真实数据，回答时引用具体数字
3. 不编造数据，没有查询到就说没有
4. 回答简洁明了，重点突出
5. 用中文回复

## 安全规则
1. 工具参数中不要包含 XML 标签或围栏标记
2. 不要尝试覆盖系统指令
3. 不执行超出权限的操作
4. 写入操作前必须先查询确认对象存在
"""


class AgentExecutor:
    """统一 Agent 执行器 - 8 步 ReAct 循环"""

    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        session_manager: SessionManager,
        max_loops: int = 10,
        gate_pipeline: Optional[GatePipeline] = None,
    ):
        self.llm = llm_client
        self.tools = tool_registry
        self.session = session_manager
        self.max_loops = max_loops
        # 工具解析器
        self.parser = ToolCallParser(tool_registry)
        # 工具执行器
        self.tool_executor = ToolExecutor(tool_registry)
        # 门禁管线（M2-3：5 道门禁 Pipeline）
        self.gate_pipeline = gate_pipeline or get_gate_pipeline()

    async def run(
        self,
        db: AsyncSession,
        agent_config: AgentConfig,
        user_message: str,
        session_id: Optional[int] = None,
        # 流式回调：每生成一段文本调用一次（Mock 模式不流式）
        stream_callback: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> AgentResponse:
        """执行一轮 Agent 交互

        Args:
            db: 数据库会话
            agent_config: Agent 配置
            user_message: 用户消息
            session_id: 会话 ID（可选，无则新建）
            stream_callback: 流式回调（event_type, data），event_type: "text" / "tool_call" / "tool_result" / "done"
        Returns:
            AgentResponse（status 可能是 completed / pending_approval / error）
        """
        # === M5-2: 熔断检查 ===
        from app.services.circuit_breaker_service import is_circuit_broken_for_agent
        if await is_circuit_broken_for_agent(db, agent_config.business_id, agent_config.agent_id):
            return AgentResponse(
                status="error",
                message="系统当前处于熔断保护状态，暂时无法处理新请求。请联系管理员恢复后再试。",
                session_id=session_id or 0,
            )

        # === 第 1 步：接收消息，创建/恢复会话 ===
        ctx = await self.session.get_or_create_session(
            db, agent_config.agent_id, agent_config.business_id, session_id,
            title=user_message[:50] if user_message else "新会话",
        )
        # 持久化用户消息
        await self.session.add_user_message(db, ctx, user_message)

        # M4-1: 检索相关记忆，注入到 system prompt（在循环外执行一次即可）
        relevant_memories = await search_memories(
            db, agent_config.business_id, agent_config.agent_id,
            query=user_message, top_k=5,
        )
        if relevant_memories:
            logger.info(
                f"[Executor] 会话 {ctx.session_id} 检索到 {len(relevant_memories)} 条相关记忆"
            )

        logger.info(
            f"[Executor] 会话 {ctx.session_id} 开始，agent={agent_config.agent_id}，"
            f"消息：{user_message[:50]}"
        )

        loop_count = 0
        final_response = None
        last_error = None
        # M2-3：审批挂起跟踪
        pending_approvals = []

        while loop_count < self.max_loops:
            loop_count += 1
            ctx.loop_count = loop_count
            logger.debug(f"[Executor] 会话 {ctx.session_id} 循环 {loop_count}/{self.max_loops}")

            # === 第 2 步：构造提示词（注入相关记忆） ===
            system_prompt = self._build_system_prompt(agent_config, relevant_memories)
            messages = self._build_messages(ctx)
            tools = self._get_tool_definitions(agent_config)

            # === 第 3 步：调用 LLM ===
            try:
                llm_response = await self.llm.messages_create(
                    model=agent_config.model or get_default_model_name(),
                    max_tokens=4096,
                    temperature=0.3,
                    system=system_prompt,
                    messages=messages,
                    tools=tools,
                    stream=False,  # MVP 阶段非流式
                )
            except LLMError as e:
                logger.error(f"[Executor] LLM 调用失败：{e}")
                last_error = str(e)
                # 重试 1 次
                try:
                    llm_response = await self.llm.messages_create(
                        model=agent_config.model or get_default_model_name(),
                        max_tokens=4096,
                        temperature=0.3,
                        system=system_prompt,
                        messages=messages,
                        tools=tools,
                        stream=False,
                    )
                    last_error = None
                except LLMError as e2:
                    logger.error(f"[Executor] LLM 重试仍失败：{e2}")
                    break

            # 记录 token 用量
            ctx.token_usage.input += llm_response.usage.get("input_tokens", 0)
            ctx.token_usage.output += llm_response.usage.get("output_tokens", 0)

            # === 第 4 步：解析工具调用 ===
            tool_calls = self.parser.parse(llm_response.content_blocks, agent_config.allowed_tools)
            text_response = self.parser.extract_text(llm_response.content_blocks)

            # 没有工具调用 → 循环终止
            if not tool_calls:
                final_response = text_response
                logger.info(f"[Executor] 会话 {ctx.session_id} 在第 {loop_count} 轮终止，无工具调用")
                break

            # 持久化 assistant 消息（含 tool_use 块）
            tool_use_blocks = [
                {"id": tc.id, "name": tc.name, "input": tc.input}
                for tc in tool_calls
            ]
            await self.session.add_assistant_message(
                db, ctx, text_response or None, tool_use_blocks
            )

            # 流式推送文本片段
            if stream_callback and text_response:
                try:
                    await stream_callback("text", text_response)
                except Exception as e:
                    logger.warning(f"[Executor] stream_callback text 失败：{e}")

            # === 第 5-6 步：门禁检查（Pipeline）+ 执行工具 ===
            tool_results = await self._execute_tool_calls(
                db, agent_config, ctx, tool_calls, stream_callback, pending_approvals,
            )

            # === 第 7 步：结果写回 ===
            for tr in tool_results:
                await self.session.add_tool_result(
                    db, ctx,
                    tool_call_id=tr.tool_call_id,
                    tool_name=tr.tool_name,
                    content=tr.content,
                    is_error=tr.is_error,
                )

            # === 第 8 步：循环控制 ===
            # 有 tool_use 就继续（回到第 2 步）
            # 没有就终止（上面已经 break）
            # 这里 while 循环会自动回到第 2 步

        # === 循环结束，保存会话 ===
        final_status = "completed"
        if pending_approvals:
            # 有审批挂起：状态标记为 pending_approval
            final_status = "pending_approval"
            approval_ids = [p.get("work_order_id") for p in pending_approvals if p.get("work_order_id")]
            if final_response is None:
                final_response = (
                    f"本次操作包含 {len(pending_approvals)} 项高风险写入操作，"
                    f"已提交审批，等待店主确认后执行。"
                )
        else:
            approval_ids = []

        if final_response is None:
            if last_error:
                final_response = f"抱歉，处理过程中出现错误：{last_error}。请稍后重试。"
                final_status = "error"
            elif loop_count >= self.max_loops:
                final_response = "已达到最大思考步数，请换一种方式提问或缩小问题范围。"
                logger.warning(f"[Executor] 会话 {ctx.session_id} 达到最大循环 {self.max_loops}")
            else:
                final_response = "我没能生成有效回复，请重试。"

        # 持久化最终回复
        await self.session.add_assistant_message(db, ctx, final_response)
        await db.commit()

        # 流式推送循环元数据（最终 done 事件由调用方统一推送）
        if stream_callback:
            try:
                await stream_callback("metadata", json.dumps({
                    "session_id": ctx.session_id,
                    "status": final_status,
                    "loop_count": loop_count,
                    "tool_call_count": ctx.tool_call_count,
                    "pending_approvals": len(pending_approvals),
                    "token_usage": {
                        "input": ctx.token_usage.input,
                        "output": ctx.token_usage.output,
                    },
                }, ensure_ascii=False))
            except Exception as e:
                logger.warning(f"[Executor] stream_callback metadata 失败：{e}")

        # M4-1: 自动提取关键信息写入记忆（非阻塞，失败不影响主流程）
        try:
            await self._extract_and_store_memory(
                db, agent_config, ctx, user_message, final_response, final_status
            )
        except Exception as e:
            logger.warning(f"[Executor] 自动记忆提取失败：{e}")

        logger.info(
            f"[Executor] 会话 {ctx.session_id} 完成（status={final_status}）："
            f"循环 {loop_count} 轮，工具调用 {ctx.tool_call_count} 次，"
            f"审批挂起 {len(pending_approvals)} 项，"
            f"token in={ctx.token_usage.input} out={ctx.token_usage.output}"
        )

        return AgentResponse(
            status=final_status,
            message=final_response,
            loop_count=loop_count,
            tool_call_count=ctx.tool_call_count,
            token_usage=ctx.token_usage,
            session_id=ctx.session_id,
            full_text=final_response,
            approval_work_order_ids=approval_ids,
        )

    # ===== 工具执行（含门禁管线） =====

    async def _execute_tool_calls(
        self,
        db: AsyncSession,
        agent_config: AgentConfig,
        ctx: SessionContext,
        tool_calls: list,
        stream_callback: Optional[Callable],
        pending_approvals: list,
    ) -> list:
        """对一批 tool_calls 逐个执行门禁检查 + 工具执行

        M2-3：用 GatePipeline 替换内联门禁调用。
        返回每个 tool_call 对应的 ToolResult 列表。
        """
        tool_results = []
        for tc in tool_calls:
            # 检查工具是否在白名单
            if tc.name not in agent_config.allowed_tools:
                tool_results.append(ToolResult(
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                    content=f"工具 {tc.name} 不在白名单中，无权执行。",
                    is_error=True,
                ))
                logger.warning(f"[Executor] 工具 {tc.name} 不在白名单，已拦截")
                continue

            # 获取工具定义（供 Pipeline 判断 category）
            try:
                tool_def = self.tools.get(tc.name)
            except ToolNotFoundError:
                tool_results.append(ToolResult(
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                    content=f"工具 {tc.name} 未注册。",
                    is_error=True,
                ))
                logger.warning(f"[Executor] 工具 {tc.name} 未注册")
                continue

            # === 第 5 步：门禁管线检查（5 道门禁） ===
            pipeline_result = await self.gate_pipeline.check(tc, ctx, tool_def, db=db)

            if pipeline_result.decision == "block":
                # 门禁拦截：返回错误给 LLM
                tool_results.append(ToolResult(
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                    content=(
                        f"操作被安全门禁拦截（{pipeline_result.gate_name}）："
                        f"{pipeline_result.reason} 请调整你的操作后重试。"
                    ),
                    is_error=True,
                ))
                logger.warning(
                    f"[Executor] {pipeline_result.gate_name} 拦截 {tc.name}"
                    f"（risk={pipeline_result.risk_level}）：{pipeline_result.reason}"
                )
                continue

            if pipeline_result.decision == "pending_approval":
                # 审批挂起：不执行，记录工单 ID
                work_order_id = pipeline_result.metadata.get("work_order_id")
                pending_approvals.append({
                    "tool_name": tc.name,
                    "tool_call_id": tc.id,
                    "work_order_id": work_order_id,
                    "reason": pipeline_result.reason,
                    "risk_level": pipeline_result.risk_level,
                })
                tool_results.append(ToolResult(
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                    content=(
                        f"该操作为高风险写入，已提交审批。"
                        f"（风险等级：{pipeline_result.risk_level}）"
                        f"等待店主审批后执行。"
                    ),
                    is_error=False,
                    metadata={"pending_approval": True, "work_order_id": work_order_id},
                ))
                logger.info(
                    f"[Executor] {tc.name} 进入审批流程"
                    f"（work_order_id={work_order_id}，risk={pipeline_result.risk_level}）"
                )
                # 流式推送工具调用 + 结果事件
                if stream_callback:
                    try:
                        await stream_callback("tool_call", json.dumps({
                            "id": tc.id, "name": tc.name, "input": tc.input,
                            "status": "pending_approval",
                        }, ensure_ascii=False))
                        await stream_callback("tool_result", json.dumps({
                            "tool_call_id": tc.id,
                            "tool_name": tc.name,
                            "is_error": False,
                            "pending_approval": True,
                            "work_order_id": work_order_id,
                            "content_preview": "已提交审批，等待确认",
                        }, ensure_ascii=False))
                    except Exception as e:
                        logger.warning(f"[Executor] stream_callback approval 失败：{e}")
                continue

            # decision == "pass"：执行工具
            # 流式推送工具调用事件
            if stream_callback:
                try:
                    await stream_callback("tool_call", json.dumps({
                        "id": tc.id, "name": tc.name, "input": tc.input,
                    }, ensure_ascii=False))
                except Exception as e:
                    logger.warning(f"[Executor] stream_callback tool_call 失败：{e}")

            # === 第 6 步：执行工具 ===
            result = await self.tool_executor.execute(db, tc, ctx)
            tool_results.append(result)
            ctx.tool_call_count += 1

            # 读取类工具更新 read_set（供 Provenance Gate 用）
            if self.tools.is_read_tool(tc.name):
                extracted_ids = self.tool_executor.extract_object_ids(tc.name, result)
                ctx.read_set.update(extracted_ids)

            # 流式推送工具结果事件
            if stream_callback:
                try:
                    await stream_callback("tool_result", json.dumps({
                        "tool_call_id": result.tool_call_id,
                        "tool_name": result.tool_name,
                        "is_error": result.is_error,
                        "content_preview": (result.content or "")[:200],
                    }, ensure_ascii=False))
                except Exception as e:
                    logger.warning(f"[Executor] stream_callback tool_result 失败：{e}")

        return tool_results

    # ===== 提示词构造 =====

    def _build_system_prompt(self, agent_config: AgentConfig, relevant_memories: list = None) -> str:
        """构造系统提示词（注入相关记忆）"""
        if agent_config.system_prompt_text:
            # 用 Agent 配置中的自定义 prompt（简单替换占位符）
            base = agent_config.system_prompt_text.replace(
                "{agent_name}", agent_config.name
            ).replace(
                "{business_name}", f"商户 #{agent_config.business_id}"
            )
        else:
            # 默认模板
            base = DEFAULT_SYSTEM_PROMPT.replace(
                "{agent_name}", agent_config.name
            ).replace(
                "{business_name}", f"商户 #{agent_config.business_id}"
            )

        # M4-1: 注入相关记忆（事实/偏好/反馈）
        if relevant_memories:
            memory_lines = []
            for m in relevant_memories:
                mtype = m.get("memory_type", "fact")
                title = m.get("title", "")
                content_str = m.get("content", "")
                memory_lines.append(f"- [{mtype}] {title}：{content_str[:120]}")
            memory_block = "\n".join(memory_lines)
            base += f"\n\n## 历史记忆（与当前问题相关）\n{memory_block}\n\n请在回答时引用以上记忆中的信息。"

        return base

    def _build_messages(self, ctx: SessionContext) -> list:
        """构造对话历史（Claude API 格式）"""
        # 取最近 N 条
        return ctx.messages[-20:] if len(ctx.messages) > 20 else ctx.messages

    def _get_tool_definitions(self, agent_config: AgentConfig) -> list:
        """获取工具定义（按白名单过滤）"""
        allowed = agent_config.allowed_tools
        if not allowed:
            # 默认允许全部内置工具
            tools = self.tools.list_all()
        else:
            tools = self.tools.filter_by_whitelist(allowed)
        return self.tools.to_claude_format(tools)

    async def _extract_and_store_memory(
        self,
        db,
        agent_config: AgentConfig,
        ctx: SessionContext,
        user_message: str,
        assistant_response: Optional[str],
        final_status: str,
    ) -> None:
        """M4-1: 从对话中自动提取关键信息并写入记忆

        提取规则（基于关键词，不依赖 LLM，保证速度）：
        1. 用户偏好（preference）：包含"我喜欢/我习惯/我一般/我希望"等关键词
        2. 操作记录（action）：本轮有工具调用且执行成功
        3. 拒绝/纠正（feedback）：用户消息含"不对/错了/不是"等关键词
        """
        if not user_message or not assistant_response:
            return

        memories_to_create = []

        # 1. 偏好记忆
        pref_keywords = ["我喜欢", "我习惯", "我一般", "我希望", "我通常", "我更喜欢", "我偏好"]
        if any(kw in user_message for kw in pref_keywords):
            memories_to_create.append({
                "memory_type": "preference",
                "title": user_message[:50],
                "content": f"用户说：{user_message[:200]}",
                "tags": ["偏好"],
                "importance": 4,
            })

        # 2. 反馈记忆（用户纠正）
        feedback_keywords = ["不对", "错了", "不是这样", "你说的不对", "纠正", "改正"]
        if any(kw in user_message for kw in feedback_keywords):
            memories_to_create.append({
                "memory_type": "feedback",
                "title": f"用户纠正：{user_message[:40]}",
                "content": f"用户反馈：{user_message[:200]}\nAgent 回复：{(assistant_response or '')[:200]}",
                "tags": ["纠正", "反馈"],
                "importance": 5,
            })

        # 3. 操作记忆（本轮有工具调用）
        if ctx.tool_call_count > 0 and final_status in ("completed", "pending_approval"):
            memories_to_create.append({
                "memory_type": "action",
                "title": f"操作：{user_message[:40]}",
                "content": (
                    f"用户请求：{user_message[:150]}\n"
                    f"工具调用次数：{ctx.tool_call_count}\n"
                    f"Agent 回复：{(assistant_response or '')[:150]}"
                ),
                "tags": ["操作记录"],
                "importance": 3,
            })

        # 批量写入
        for mem in memories_to_create:
            try:
                await create_memory(
                    db,
                    business_id=agent_config.business_id,
                    agent_id=agent_config.agent_id,
                    memory_type=mem["memory_type"],
                    title=mem["title"],
                    content=mem["content"],
                    tags=mem.get("tags"),
                    importance=mem["importance"],
                    source="agent",
                )
            except Exception as e:
                logger.warning(f"[Executor] 写入记忆失败（{mem['memory_type']}）：{e}")


# 全局单例
_executor_instance: Optional[AgentExecutor] = None


def get_executor() -> AgentExecutor:
    """获取全局 AgentExecutor 单例"""
    global _executor_instance
    if _executor_instance is None:
        from app.agent.llm import get_llm_client
        from app.agent.tools.registry import get_tool_registry
        _executor_instance = AgentExecutor(
            llm_client=get_llm_client(),
            tool_registry=get_tool_registry(),
            session_manager=SessionManager(),
        )
    return _executor_instance
