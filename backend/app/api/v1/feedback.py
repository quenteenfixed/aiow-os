"""反馈学习 API 路由 - 反馈统计、策略建议、策略版本管理、自主级别

权限：
- feedback:read  - 查看统计、策略、建议
- feedback:write - 更新策略、回滚、调整自主级别
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.api.response import success_response
from app.database import get_db
from app.services.feedback_service import (
    get_feedback_stats, generate_strategy_suggestion,
    get_strategy, update_strategy, rollback_strategy,
    set_autonomy_level, AUTONOMY_LEVEL_DESC,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class StrategyUpdateRequest(BaseModel):
    """策略更新"""
    strategy: dict = Field(..., description="策略配置")
    note: str = Field("", max_length=500, description="更新备注")


class AutonomyLevelRequest(BaseModel):
    """自主级别调整"""
    autonomy_level: str = Field(..., description="L0/L1/L2/L3/L4")


@router.get("/stats", response_model=None)
async def feedback_stats_api(
    request: Request,
    agent_id: int = Query(..., description="Agent ID"),
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    user: CurrentUser = Depends(require_permission("feedback:read")),
    db: AsyncSession = Depends(get_db),
):
    """审批反馈统计：通过率趋势 + 按类型统计"""
    stats = await get_feedback_stats(db, user.business_id, agent_id, days)
    return success_response(stats, request_id=request.state.request_id)


@router.get("/suggestions", response_model=None)
async def strategy_suggestions_api(
    request: Request,
    agent_id: int = Query(..., description="Agent ID"),
    user: CurrentUser = Depends(require_permission("feedback:read")),
    db: AsyncSession = Depends(get_db),
):
    """基于反馈生成策略调整建议"""
    result = await generate_strategy_suggestion(db, user.business_id, agent_id)
    return success_response(result, request_id=request.state.request_id)


@router.get("/strategy", response_model=None)
async def get_strategy_api(
    request: Request,
    agent_id: int = Query(..., description="Agent ID"),
    user: CurrentUser = Depends(require_permission("feedback:read")),
    db: AsyncSession = Depends(get_db),
):
    """获取当前策略及历史版本"""
    strategy = await get_strategy(db, user.business_id, agent_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return success_response(strategy, request_id=request.state.request_id)


@router.put("/strategy", response_model=None)
async def update_strategy_api(
    req: StrategyUpdateRequest,
    request: Request,
    agent_id: int = Query(..., description="Agent ID"),
    user: CurrentUser = Depends(require_permission("feedback:write")),
    db: AsyncSession = Depends(get_db),
):
    """更新策略（版本号 +1）"""
    result, err = await update_strategy(
        db, user.business_id, agent_id, req.strategy, req.note,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)
    return success_response(result, request_id=request.state.request_id)


@router.post("/strategy/rollback", response_model=None)
async def rollback_strategy_api(
    request: Request,
    agent_id: int = Query(..., description="Agent ID"),
    version: int = Query(..., description="目标版本号"),
    user: CurrentUser = Depends(require_permission("feedback:write")),
    db: AsyncSession = Depends(get_db),
):
    """回滚到指定策略版本"""
    result, err = await rollback_strategy(db, user.business_id, agent_id, version)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return success_response(result, request_id=request.state.request_id)


@router.put("/autonomy", response_model=None)
async def set_autonomy_api(
    req: AutonomyLevelRequest,
    request: Request,
    agent_id: int = Query(..., description="Agent ID"),
    user: CurrentUser = Depends(require_permission("feedback:write")),
    db: AsyncSession = Depends(get_db),
):
    """调整 Agent 自主级别 L0-L4"""
    agent, err = await set_autonomy_level(
        db, user.business_id, agent_id, req.autonomy_level,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)
    data = {
        "agent_id": agent_id,
        "autonomy_level": agent.autonomy_level,
        "description": AUTONOMY_LEVEL_DESC.get(agent.autonomy_level, ""),
    }
    return success_response(data, request_id=request.state.request_id)


@router.get("/autonomy/levels", response_model=None)
async def autonomy_levels_api(
    request: Request,
    user: CurrentUser = Depends(require_permission("feedback:read")),
):
    """获取自主级别说明"""
    return success_response(AUTONOMY_LEVEL_DESC, request_id=request.state.request_id)
