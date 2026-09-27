"""记忆系统 API 路由 - CRUD + 检索 + 统计

权限：
- memory:read  - 查看/检索记忆
- memory:write - 创建/更新/删除记忆
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_pagination, require_permission
from app.api.response import success_response
from app.database import get_db
from app.schemas.memory import MemoryCreate, MemoryUpdate, MemorySearch
from app.services.memory_service import (
    create_memory, list_memories, get_memory, update_memory,
    delete_memory, search_memories, get_memory_stats,
    _memory_dict,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# 注意：记忆属于 Agent，所以路径上需要 agent_id
# 但用户可以有多个 Agent，这里用 query 参数 agent_id 过滤


@router.get("", response_model=None)
async def list_memories_api(
    request: Request,
    agent_id: int = Query(..., description="Agent ID"),
    memory_type: str = Query(None, description="按类型筛选：fact/preference/action/feedback"),
    source: str = Query(None, description="按来源筛选"),
    pagination: Depends = Depends(get_pagination),
    user: CurrentUser = Depends(require_permission("memory:read")),
    db: AsyncSession = Depends(get_db),
):
    """记忆列表"""
    items, total = await list_memories(
        db, user.business_id, agent_id,
        memory_type=memory_type, source=source,
        page=pagination.page, page_size=pagination.page_size,
    )
    total_pages = (total + pagination.page_size - 1) // pagination.page_size if pagination.page_size > 0 else 0
    data = {
        "items": items, "total": total,
        "page": pagination.page, "page_size": pagination.page_size,
        "total_pages": total_pages,
    }
    return success_response(data, request_id=request.state.request_id)


@router.get("/stats", response_model=None)
async def memory_stats_api(
    request: Request,
    agent_id: int = Query(..., description="Agent ID"),
    user: CurrentUser = Depends(require_permission("memory:read")),
    db: AsyncSession = Depends(get_db),
):
    """记忆统计"""
    stats = await get_memory_stats(db, user.business_id, agent_id)
    return success_response(stats, request_id=request.state.request_id)


@router.get("/search", response_model=None)
async def search_memories_api(
    request: Request,
    agent_id: int = Query(..., description="Agent ID"),
    query: str = Query(..., description="搜索关键词"),
    memory_type: Optional[str] = Query(None, description="记忆类型"),
    tags: Optional[str] = Query(None, description="标签，逗号分隔"),
    top_k: int = Query(10, ge=1, le=50),
    user: CurrentUser = Depends(require_permission("memory:read")),
    db: AsyncSession = Depends(get_db),
):
    """记忆检索（关键词匹配，返回相关度分数）"""
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    items = await search_memories(
        db, user.business_id, agent_id,
        query=query,
        memory_type=memory_type,
        tags=tag_list,
        top_k=top_k,
    )
    data = {"items": items, "total": len(items)}
    return success_response(data, request_id=request.state.request_id)


@router.get("/{memory_id}", response_model=None)
async def get_memory_api(
    memory_id: int,
    request: Request,
    agent_id: int = Query(..., description="Agent ID"),
    user: CurrentUser = Depends(require_permission("memory:read")),
    db: AsyncSession = Depends(get_db),
):
    """记忆详情"""
    memory = await get_memory(db, user.business_id, agent_id, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="记忆不存在或无权访问")
    data = _memory_dict(memory)
    return success_response(data, request_id=request.state.request_id)


@router.post("", response_model=None)
async def create_memory_api(
    req: MemoryCreate,
    request: Request,
    agent_id: int = Query(..., description="Agent ID"),
    user: CurrentUser = Depends(require_permission("memory:write")),
    db: AsyncSession = Depends(get_db),
):
    """创建记忆"""
    try:
        memory = await create_memory(
            db, user.business_id, agent_id,
            memory_type=req.memory_type,
            title=req.title,
            content=req.content,
            tags=req.tags,
            importance=req.importance,
            source=req.source or "manual",
            ttl_hours=req.ttl_hours,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    data = _memory_dict(memory)
    return success_response(data, request_id=request.state.request_id)


@router.patch("/{memory_id}", response_model=None)
async def update_memory_api(
    memory_id: int,
    req: MemoryUpdate,
    request: Request,
    agent_id: int = Query(..., description="Agent ID"),
    user: CurrentUser = Depends(require_permission("memory:write")),
    db: AsyncSession = Depends(get_db),
):
    """更新记忆"""
    memory, err = await update_memory(
        db, user.business_id, agent_id, memory_id,
        title=req.title,
        content=req.content,
        tags=req.tags,
        importance=req.importance,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)
    data = _memory_dict(memory)
    return success_response(data, request_id=request.state.request_id)


@router.delete("/{memory_id}", response_model=None)
async def delete_memory_api(
    memory_id: int,
    request: Request,
    agent_id: int = Query(..., description="Agent ID"),
    user: CurrentUser = Depends(require_permission("memory:write")),
    db: AsyncSession = Depends(get_db),
):
    """删除记忆"""
    ok, err = await delete_memory(db, user.business_id, agent_id, memory_id)
    if err:
        raise HTTPException(status_code=404, detail=err)
    return success_response({"deleted": True}, request_id=request.state.request_id)
