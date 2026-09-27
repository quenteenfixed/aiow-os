"""告警 API 路由 - 列表/详情/确认/解决/统计

权限：
- alert:read  - 查看告警
- alert:write - 确认/解决告警
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_pagination, require_permission
from app.api.response import success_response
from app.database import get_db
from app.schemas.alert import AlertAcknowledge, AlertResolve
from app.services.alert_service import (
    list_alerts, get_alert, acknowledge_alert, resolve_alert,
    get_alert_stats, _alert_dict,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=None)
async def list_alerts_api(
    request: Request,
    status: str = Query(None, description="按状态筛选：active/acknowledged/resolved"),
    level: str = Query(None, description="按级别筛选：P0/P1/P2/P3"),
    alert_type: str = Query(None, description="按类型筛选：inventory/sales/expiring/system"),
    source: str = Query(None, description="按来源筛选：system/agent/loop"),
    pagination: Depends = Depends(get_pagination),
    user: CurrentUser = Depends(require_permission("alert:read")),
    db: AsyncSession = Depends(get_db),
):
    """告警列表（支持多维度筛选）"""
    items, total = await list_alerts(
        db, user.business_id,
        status=status, level=level, alert_type=alert_type, source=source,
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
async def alert_stats_api(
    request: Request,
    user: CurrentUser = Depends(require_permission("alert:read")),
    db: AsyncSession = Depends(get_db),
):
    """告警统计：按 status/level/type 聚合"""
    stats = await get_alert_stats(db, user.business_id)
    return success_response(stats, request_id=request.state.request_id)


@router.get("/{alert_id}", response_model=None)
async def get_alert_api(
    alert_id: int,
    request: Request,
    user: CurrentUser = Depends(require_permission("alert:read")),
    db: AsyncSession = Depends(get_db),
):
    """告警详情"""
    alert = await get_alert(db, user.business_id, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="告警不存在或无权访问")
    data = _alert_dict(alert)
    return success_response(data, request_id=request.state.request_id)


@router.post("/{alert_id}/acknowledge", response_model=None)
async def acknowledge_alert_api(
    alert_id: int,
    req: AlertAcknowledge,
    request: Request,
    user: CurrentUser = Depends(require_permission("alert:write")),
    db: AsyncSession = Depends(get_db),
):
    """确认告警：active → acknowledged"""
    alert, err = await acknowledge_alert(
        db, user.business_id, alert_id, user.user_id, req.comment,
    )
    if err:
        raise HTTPException(status_code=409, detail=err)
    data = _alert_dict(alert)
    return success_response(data, request_id=request.state.request_id)


@router.post("/{alert_id}/resolve", response_model=None)
async def resolve_alert_api(
    alert_id: int,
    req: AlertResolve,
    request: Request,
    user: CurrentUser = Depends(require_permission("alert:write")),
    db: AsyncSession = Depends(get_db),
):
    """解决告警：active/acknowledged → resolved"""
    alert, err = await resolve_alert(
        db, user.business_id, alert_id, user.user_id, req.comment,
    )
    if err:
        raise HTTPException(status_code=409, detail=err)
    data = _alert_dict(alert)
    return success_response(data, request_id=request.state.request_id)
