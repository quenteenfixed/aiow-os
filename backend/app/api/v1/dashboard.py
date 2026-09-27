"""管理仪表盘 API 路由

权限：
- dashboard:read - 查看仪表盘数据
"""
import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.api.response import success_response
from app.database import get_db
from app.services.dashboard_service import (
    get_overview, get_sales_trend, get_inventory_trend,
    get_agent_activity, get_efficiency_comparison,
    get_alerts_summary, get_full_dashboard,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/overview", response_model=None)
async def dashboard_overview_api(
    request: Request,
    days: int = Query(7, ge=1, le=365, description="统计天数"),
    user: CurrentUser = Depends(require_permission("dashboard:read")),
    db: AsyncSession = Depends(get_db),
):
    """经营总览：销售额、订单、库存、工单、告警、Agent 分布"""
    data = await get_overview(db, user.business_id, days)
    return success_response(data, request_id=request.state.request_id)


@router.get("/sales-trend", response_model=None)
async def sales_trend_api(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    granularity: str = Query("day", pattern="^(day|week|month)$"),
    user: CurrentUser = Depends(require_permission("dashboard:read")),
    db: AsyncSession = Depends(get_db),
):
    """销售趋势（按日/周/月）"""
    data = await get_sales_trend(db, user.business_id, days, granularity)
    return success_response(data, request_id=request.state.request_id)


@router.get("/inventory-trend", response_model=None)
async def inventory_trend_api(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    user: CurrentUser = Depends(require_permission("dashboard:read")),
    db: AsyncSession = Depends(get_db),
):
    """库存出入库趋势"""
    data = await get_inventory_trend(db, user.business_id, days)
    return success_response(data, request_id=request.state.request_id)


@router.get("/agent-activity", response_model=None)
async def agent_activity_api(
    request: Request,
    days: int = Query(7, ge=1, le=365),
    user: CurrentUser = Depends(require_permission("dashboard:read")),
    db: AsyncSession = Depends(get_db),
):
    """Agent 活动统计"""
    data = await get_agent_activity(db, user.business_id, days)
    return success_response(data, request_id=request.state.request_id)


@router.get("/efficiency", response_model=None)
async def efficiency_api(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    user: CurrentUser = Depends(require_permission("dashboard:read")),
    db: AsyncSession = Depends(get_db),
):
    """Agent vs 人工效率对比"""
    data = await get_efficiency_comparison(db, user.business_id, days)
    return success_response(data, request_id=request.state.request_id)


@router.get("/alerts", response_model=None)
async def alerts_summary_api(
    request: Request,
    user: CurrentUser = Depends(require_permission("dashboard:read")),
    db: AsyncSession = Depends(get_db),
):
    """告警汇总"""
    data = await get_alerts_summary(db, user.business_id)
    return success_response(data, request_id=request.state.request_id)


@router.get("", response_model=None)
async def full_dashboard_api(
    request: Request,
    days: int = Query(7, ge=1, le=365),
    user: CurrentUser = Depends(require_permission("dashboard:read")),
    db: AsyncSession = Depends(get_db),
):
    """完整仪表盘数据（一次性返回所有指标）"""
    data = await get_full_dashboard(db, user.business_id, days)
    return success_response(data, request_id=request.state.request_id)
