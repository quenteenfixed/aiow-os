"""审计日志 API - M5-3"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.api.response import success_response
from app.database import get_db
from app.services.audit_service import (
    list_audit_logs, get_audit_stats, verify_chain,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/logs")
async def audit_logs_api(
    request: Request,
    actor_type: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    actor_id: Optional[int] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(require_permission("audit:read")),
    db: AsyncSession = Depends(get_db),
):
    """审计日志查询（多维度筛选 + 分页）"""
    items, total = await list_audit_logs(
        db, user.business_id, actor_type, action, target_type,
        actor_id, start_date, end_date, page, page_size,
    )
    return success_response(
        {"items": items, "total": total, "page": page, "page_size": page_size},
        request_id=request.state.request_id,
    )


@router.get("/stats")
async def audit_stats_api(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    user: CurrentUser = Depends(require_permission("audit:read")),
    db: AsyncSession = Depends(get_db),
):
    """审计统计"""
    data = await get_audit_stats(db, user.business_id, days)
    return success_response(data, request_id=request.state.request_id)


@router.post("/verify")
async def audit_verify_api(
    request: Request,
    user: CurrentUser = Depends(require_permission("audit:read")),
    db: AsyncSession = Depends(get_db),
):
    """校验审计哈希链完整性"""
    result = await verify_chain(db, user.business_id)
    return success_response(result, request_id=request.state.request_id)
