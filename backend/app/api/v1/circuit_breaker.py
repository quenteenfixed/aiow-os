"""熔断系统 API - M5-2"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.api.response import success_response
from app.database import get_db
from app.services.circuit_breaker_service import (
    get_circuit_breaker_status, list_circuit_breaks,
    recover_circuit_breaker, trigger_circuit_breaker,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class RecoverRequest(BaseModel):
    circuit_break_id: int = Field(...)
    recovery_note: str = Field(..., min_length=1, max_length=500)


class TriggerRequest(BaseModel):
    """手动触发熔断（测试/紧急用）"""
    level: str = Field(..., pattern="^(agent|system)$")
    reason: str = Field(..., min_length=1, max_length=256)
    trigger_type: str = Field("manual", max_length=64)
    agent_id: Optional[int] = None


@router.get("/status")
async def circuit_status_api(
    request: Request,
    user: CurrentUser = Depends(require_permission("circuit:read")),
    db: AsyncSession = Depends(get_db),
):
    """获取熔断状态总览"""
    data = await get_circuit_breaker_status(db, user.business_id)
    return success_response(data, request_id=request.state.request_id)


@router.get("/logs")
async def circuit_logs_api(
    request: Request,
    status: Optional[str] = Query(None, pattern="^(active|resolved)$"),
    level: Optional[str] = Query(None, pattern="^(agent|system)$"),
    limit: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(require_permission("circuit:read")),
    db: AsyncSession = Depends(get_db),
):
    """查询熔断记录"""
    data = await list_circuit_breaks(db, user.business_id, status, level, limit)
    return success_response(data, request_id=request.state.request_id)


@router.post("/recover")
async def circuit_recover_api(
    req: RecoverRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("circuit:write")),
    db: AsyncSession = Depends(get_db),
):
    """人工恢复熔断（需填写恢复原因）"""
    cb, err = await recover_circuit_breaker(
        db, user.business_id, req.circuit_break_id,
        recovered_by=user.user_id,
        recovery_note=req.recovery_note,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)
    return success_response(
        {"id": cb.id, "status": cb.status, "recovered_at": cb.recovered_at.isoformat() if cb.recovered_at else None},
        request_id=request.state.request_id,
    )


@router.post("/trigger")
async def circuit_trigger_api(
    req: TriggerRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("circuit:write")),
    db: AsyncSession = Depends(get_db),
):
    """手动触发熔断（紧急/测试用）"""
    cb = await trigger_circuit_breaker(
        db, user.business_id,
        level=req.level,
        trigger_type=req.trigger_type,
        reason=req.reason,
        agent_id=req.agent_id,
    )
    return success_response(
        {"id": cb.id, "status": cb.status, "level": cb.level},
        request_id=request.state.request_id,
    )
