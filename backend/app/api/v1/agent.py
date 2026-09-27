"""Agent API 路由 - CRUD + 聊天（非流式 + SSE 流式）"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_pagination, require_business_access, require_permission
from app.api.response import success_response
from app.database import get_db
from app.schemas.agent import AgentCreate, AgentUpdate, ChatRequest, SessionCreate
from app.services.agent_service import (
    chat_with_agent,
    chat_with_agent_stream,
    create_agent,
    create_session,
    close_session,
    delete_agent,
    get_agent,
    list_agents,
    list_messages,
    list_sessions,
    update_agent,
    _agent_dict,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ===== CRUD =====

@router.get("", response_model=None)
async def list_agents_api(
    request: Request,
    status: str = Query(None, description="按状态过滤"),
    pagination: Depends = Depends(get_pagination),
    user: CurrentUser = Depends(require_permission("agent:read")),
    db: AsyncSession = Depends(get_db),
):
    """Agent 列表"""
    biz = user.business_id
    items, total = await list_agents(db, biz, status, pagination.page, pagination.page_size)
    total_pages = (total + pagination.page_size - 1) // pagination.page_size if pagination.page_size > 0 else 0
    data = {"items": items, "total": total, "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages}
    return success_response(data, request_id=request.state.request_id)


@router.post("", response_model=None)
async def create_agent_api(
    req: AgentCreate,
    request: Request,
    user: CurrentUser = Depends(require_permission("agent:write")),
    db: AsyncSession = Depends(get_db),
):
    """创建 Agent"""
    agent = await create_agent(db, user.business_id, req)
    data = _agent_dict(agent)
    return success_response(data, request_id=request.state.request_id)


@router.get("/{agent_id}", response_model=None)
async def get_agent_api(
    agent_id: int,
    request: Request,
    user: CurrentUser = Depends(require_permission("agent:read")),
    db: AsyncSession = Depends(get_db),
):
    """Agent 详情"""
    agent = await get_agent(db, user.business_id, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    data = _agent_dict(agent)
    return success_response(data, request_id=request.state.request_id)


@router.put("/{agent_id}", response_model=None)
async def update_agent_api(
    agent_id: int,
    req: AgentUpdate,
    request: Request,
    user: CurrentUser = Depends(require_permission("agent:write")),
    db: AsyncSession = Depends(get_db),
):
    """更新 Agent"""
    agent = await update_agent(db, user.business_id, agent_id, req)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    data = _agent_dict(agent)
    return success_response(data, request_id=request.state.request_id)


@router.delete("/{agent_id}", response_model=None)
async def delete_agent_api(
    agent_id: int,
    request: Request,
    user: CurrentUser = Depends(require_permission("agent:write")),
    db: AsyncSession = Depends(get_db),
):
    """停用 Agent（status=stopped）"""
    agent = await delete_agent(db, user.business_id, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    data = {"id": agent.id, "status": agent.status}
    return success_response(data, request_id=request.state.request_id)


# ===== 会话 =====

@router.get("/{agent_id}/sessions", response_model=None)
async def list_sessions_api(
    agent_id: int,
    request: Request,
    status: str = Query(None),
    pagination: Depends = Depends(get_pagination),
    user: CurrentUser = Depends(require_permission("agent:read")),
    db: AsyncSession = Depends(get_db),
):
    """Agent 的会话列表"""
    items, total = await list_sessions(
        db, user.business_id, agent_id, status,
        pagination.page, pagination.page_size,
    )
    total_pages = (total + pagination.page_size - 1) // pagination.page_size if pagination.page_size > 0 else 0
    data = {"items": items, "total": total, "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages}
    return success_response(data, request_id=request.state.request_id)


@router.post("/{agent_id}/sessions", response_model=None)
async def create_session_api(
    agent_id: int,
    req: SessionCreate,
    request: Request,
    user: CurrentUser = Depends(require_permission("agent:write")),
    db: AsyncSession = Depends(get_db),
):
    """创建空会话（不发送消息，前端可预创建会话获取 session_id）"""
    try:
        sess = await create_session(
            db, user.business_id, agent_id,
            title=req.title, session_type=req.session_type,
        )
    except ValueError as e:
        msg = str(e)
        if "不存在" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=409, detail=msg)
    if sess is None:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    data = {
        "id": sess.id, "agent_id": sess.agent_id,
        "session_type": sess.session_type, "title": sess.title,
        "status": sess.status,
        "created_at": sess.created_at.isoformat() if sess.created_at else None,
    }
    return success_response(data, request_id=request.state.request_id)


@router.delete("/{agent_id}/sessions/{session_id}", response_model=None)
async def close_session_api(
    agent_id: int,
    session_id: int,
    request: Request,
    user: CurrentUser = Depends(require_permission("agent:write")),
    db: AsyncSession = Depends(get_db),
):
    """关闭会话（status=closed，软关闭，不删除消息）"""
    sess = await close_session(db, user.business_id, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")
    data = {"id": sess.id, "status": sess.status, "closed_at": sess.closed_at.isoformat() if sess.closed_at else None}
    return success_response(data, request_id=request.state.request_id)


@router.get("/sessions/{session_id}/messages", response_model=None)
async def list_messages_api(
    session_id: int,
    request: Request,
    pagination: Depends = Depends(get_pagination),
    user: CurrentUser = Depends(require_permission("agent:read")),
    db: AsyncSession = Depends(get_db),
):
    """查询会话消息历史"""
    items, total = await list_messages(
        db, user.business_id, session_id,
        pagination.page, pagination.page_size,
    )
    total_pages = (total + pagination.page_size - 1) // pagination.page_size if pagination.page_size > 0 else 0
    data = {"items": items, "total": total, "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages}
    return success_response(data, request_id=request.state.request_id)


# ===== 聊天 =====

@router.post("/{agent_id}/chat", response_model=None)
async def chat_api(
    agent_id: int,
    req: ChatRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("agent:read")),
    db: AsyncSession = Depends(get_db),
):
    """非流式聊天"""
    try:
        response = await chat_with_agent(
            db, user.business_id, agent_id,
            message=req.message, session_id=req.session_id,
        )
    except ValueError as e:
        # Agent 不存在或状态不允许
        msg = str(e)
        if "不存在" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=409, detail=msg)

    data = {
        "session_id": response.session_id,
        "status": response.status,
        "message": response.message,
        "loop_count": response.loop_count,
        "tool_call_count": response.tool_call_count,
        "token_usage": {
            "input": response.token_usage.input,
            "output": response.token_usage.output,
        },
    }
    return success_response(data, request_id=request.state.request_id)


@router.post("/{agent_id}/chat/stream", response_model=None)
async def chat_stream_api(
    agent_id: int,
    req: ChatRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("agent:read")),
    db: AsyncSession = Depends(get_db),
):
    """SSE 流式聊天

    事件格式：
    - event: text, data: 文本片段
    - event: tool_call, data: {"id","name","input"}
    - event: tool_result, data: {"tool_call_id","tool_name","is_error","content_preview"}
    - event: done, data: {"session_id","final_message"}
    - event: error, data: 错误信息
    """
    # SSE 事件 ID 计数器（支持客户端断线重连时通过 Last-Event-ID 恢复）
    event_seq = 0

    async def sse_generator():
        nonlocal event_seq
        # 首行发送 retry 指令（客户端断线后重连间隔，毫秒）
        yield f"retry: 3000\n\n"
        try:
            async for event_type, data in chat_with_agent_stream(
                db, user.business_id, agent_id,
                message=req.message, session_id=req.session_id,
            ):
                event_name = {
                    "text": "text",
                    "tool_call": "tool_call",
                    "tool_result": "tool_result",
                    "done": "done",
                    "error": "error",
                }.get(event_type, event_type)
                payload = json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else data
                event_seq += 1
                # SSE 格式：id + event + data（id 供客户端 Last-Event-ID 恢复）
                yield f"id: {event_seq}\nevent: {event_name}\ndata: {payload}\n\n"
        except Exception as e:
            logger.error(f"[chat_stream] 异常：{e}", exc_info=True)
            event_seq += 1
            yield f"id: {event_seq}\nevent: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
