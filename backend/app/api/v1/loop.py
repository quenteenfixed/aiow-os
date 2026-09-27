"""OUPDEL 循环 API 路由 - 配置 CRUD + 手动触发 + 启停 + 运行记录查询

权限：
- loop:read  - 查看循环配置/运行记录
- loop:write - 创建/更新/启停/手动触发
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_pagination, require_permission
from app.api.response import success_response
from app.database import get_db
from app.schemas.loop import (
    LoopCreate, LoopUpdate, TriggerRequest,
)
from app.services.loop_service import (
    create_loop, get_or_create_loop, list_loops, get_loop, update_loop,
    list_runs, get_run,
    _loop_dict, _run_dict,
)
from app.agent.loop.scheduler import get_scheduler

logger = logging.getLogger(__name__)

router = APIRouter()


# ===== 循环配置 =====

@router.get("", response_model=None)
async def list_loops_api(
    request: Request,
    agent_id: int = Query(None, description="按 Agent 筛选"),
    enabled: bool = Query(None, description="按启用状态筛选"),
    pagination: Depends = Depends(get_pagination),
    user: CurrentUser = Depends(require_permission("loop:read")),
    db: AsyncSession = Depends(get_db),
):
    """循环配置列表"""
    items, total = await list_loops(
        db, user.business_id, agent_id, enabled,
        pagination.page, pagination.page_size,
    )
    total_pages = (total + pagination.page_size - 1) // pagination.page_size if pagination.page_size > 0 else 0
    data = {
        "items": items, "total": total,
        "page": pagination.page, "page_size": pagination.page_size,
        "total_pages": total_pages,
    }
    return success_response(data, request_id=request.state.request_id)


@router.post("", response_model=None)
async def create_loop_api(
    req: LoopCreate,
    request: Request,
    user: CurrentUser = Depends(require_permission("loop:write")),
    db: AsyncSession = Depends(get_db),
):
    """创建循环配置（每个 Agent 只能有一份，重复创建会唯一约束报错）"""
    try:
        loop = await create_loop(
            db, user.business_id, req.agent_id,
            name=req.name,
            enabled=req.enabled,
            interval_minutes=req.interval_minutes,
            sensitivity=req.sensitivity,
            autonomy_level=req.autonomy_level,
            config=req.config,
        )
    except Exception as e:
        if "unique" in str(e).lower() or "uk_agent_loops_agent_id" in str(e).lower():
            raise HTTPException(
                status_code=409,
                detail=f"Agent {req.agent_id} 已存在循环配置，请改用更新接口",
            )
        raise HTTPException(status_code=400, detail=str(e))
    data = _loop_dict(loop)
    return success_response(data, request_id=request.state.request_id)


@router.get("/{loop_id}", response_model=None)
async def get_loop_api(
    loop_id: int,
    request: Request,
    user: CurrentUser = Depends(require_permission("loop:read")),
    db: AsyncSession = Depends(get_db),
):
    """循环配置详情"""
    loop = await get_loop(db, user.business_id, loop_id)
    if loop is None:
        raise HTTPException(status_code=404, detail="循环不存在或无权访问")
    data = _loop_dict(loop)
    return success_response(data, request_id=request.state.request_id)


@router.patch("/{loop_id}", response_model=None)
async def update_loop_api(
    loop_id: int,
    req: LoopUpdate,
    request: Request,
    user: CurrentUser = Depends(require_permission("loop:write")),
    db: AsyncSession = Depends(get_db),
):
    """更新循环配置（频率、灵敏度、自主级别、配置）"""
    loop, err = await update_loop(
        db, user.business_id, loop_id,
        name=req.name,
        enabled=req.enabled,
        interval_minutes=req.interval_minutes,
        sensitivity=req.sensitivity,
        autonomy_level=req.autonomy_level,
        config=req.config,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)
    data = _loop_dict(loop)
    return success_response(data, request_id=request.state.request_id)


@router.post("/{loop_id}/pause", response_model=None)
async def pause_loop_api(
    loop_id: int,
    request: Request,
    user: CurrentUser = Depends(require_permission("loop:write")),
    db: AsyncSession = Depends(get_db),
):
    """暂停循环：enabled=False，并通知 scheduler"""
    loop, err = await update_loop(db, user.business_id, loop_id, enabled=False)
    if err:
        raise HTTPException(status_code=400, detail=err)
    scheduler = get_scheduler()
    scheduler.pause_loop(loop.id)
    data = _loop_dict(loop)
    data["scheduler_paused"] = True
    return success_response(data, request_id=request.state.request_id)


@router.post("/{loop_id}/resume", response_model=None)
async def resume_loop_api(
    loop_id: int,
    request: Request,
    user: CurrentUser = Depends(require_permission("loop:write")),
    db: AsyncSession = Depends(get_db),
):
    """恢复循环：enabled=True，并通知 scheduler"""
    loop, err = await update_loop(db, user.business_id, loop_id, enabled=True)
    if err:
        raise HTTPException(status_code=400, detail=err)
    scheduler = get_scheduler()
    scheduler.resume_loop(loop.id)
    data = _loop_dict(loop)
    data["scheduler_resumed"] = True
    return success_response(data, request_id=request.state.request_id)


# ===== 手动触发 =====

@router.post("/trigger", response_model=None)
async def trigger_loop_api(
    req: TriggerRequest,
    request: Request,
    agent_id: int = Query(..., description="Agent ID"),
    user: CurrentUser = Depends(require_permission("loop:write")),
    db: AsyncSession = Depends(get_db),
):
    """手动触发一次 OUPDEL 循环（不受 enabled 限制，用于测试）"""
    # 确保循环配置存在
    loop = await get_or_create_loop(db, user.business_id, agent_id)
    scheduler = get_scheduler()
    result = await scheduler.trigger_loop(
        user.business_id, agent_id, trigger_type=req.trigger_type,
    )
    data = {
        "loop_id": loop.id,
        "agent_id": agent_id,
        **result,
    }
    return success_response(data, request_id=request.state.request_id)


# ===== 运行记录 =====

@router.get("/{loop_id}/runs", response_model=None)
async def list_runs_api(
    loop_id: int,
    request: Request,
    run_status: str = Query(None, description="按状态筛选"),
    pagination: Depends = Depends(get_pagination),
    user: CurrentUser = Depends(require_permission("loop:read")),
    db: AsyncSession = Depends(get_db),
):
    """循环运行记录列表"""
    items, total = await list_runs(
        db, user.business_id, loop_id=loop_id, run_status=run_status,
        page=pagination.page, page_size=pagination.page_size,
    )
    total_pages = (total + pagination.page_size - 1) // pagination.page_size if pagination.page_size > 0 else 0
    data = {
        "items": items, "total": total,
        "page": pagination.page, "page_size": pagination.page_size,
        "total_pages": total_pages,
    }
    return success_response(data, request_id=request.state.request_id)


@router.get("/runs/{run_id}", response_model=None)
async def get_run_api(
    run_id: int,
    request: Request,
    user: CurrentUser = Depends(require_permission("loop:read")),
    db: AsyncSession = Depends(get_db),
):
    """运行记录详情（含 OUPDEL 各步骤产物）"""
    run = await get_run(db, user.business_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行记录不存在或无权访问")
    data = _run_dict(run)
    return success_response(data, request_id=request.state.request_id)
