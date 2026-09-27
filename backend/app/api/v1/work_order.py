"""工单 API 路由 - CRUD + 审批 + 执行"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_pagination, require_permission
from app.api.response import success_response
from app.database import get_db
from app.schemas.work_order import (
    WorkOrderCreate, ApprovalRequest, CancelRequest, ExecutionResult,
)
from app.services.work_order_service import (
    create_work_order,
    list_work_orders,
    get_work_order,
    approve_work_order,
    reject_work_order,
    cancel_work_order,
    start_execution,
    complete_execution,
    _work_order_dict,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=None)
async def list_work_orders_api(
    request: Request,
    status: str = Query(None, description="按状态筛选"),
    order_type: str = Query(None, description="按操作类型筛选"),
    risk_level: str = Query(None, description="按风险等级筛选"),
    agent_id: int = Query(None, description="按 Agent 筛选"),
    pagination: Depends = Depends(get_pagination),
    user: CurrentUser = Depends(require_permission("work_order:read")),
    db: AsyncSession = Depends(get_db),
):
    """工单列表（支持多维度筛选）"""
    items, total = await list_work_orders(
        db, user.business_id, status, order_type, risk_level, agent_id,
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
async def create_work_order_api(
    req: WorkOrderCreate,
    request: Request,
    agent_id: int = Query(..., description="提交工单的 Agent ID"),
    user: CurrentUser = Depends(require_permission("work_order:write")),
    db: AsyncSession = Depends(get_db),
):
    """Agent 创建工单"""
    wo = await create_work_order(
        db, user.business_id, agent_id,
        order_type=req.order_type,
        title=req.title,
        description=req.description,
        reason=req.reason,
        expected_effect=req.expected_effect,
        risk_level=req.risk_level,
        params=req.params,
    )
    data = _work_order_dict(wo, include_relations=False)
    return success_response(data, request_id=request.state.request_id)


@router.get("/{work_order_id}", response_model=None)
async def get_work_order_api(
    work_order_id: int,
    request: Request,
    user: CurrentUser = Depends(require_permission("work_order:read")),
    db: AsyncSession = Depends(get_db),
):
    """工单详情（含审批历史 + 执行结果）"""
    wo = await get_work_order(db, user.business_id, work_order_id)
    if wo is None:
        raise HTTPException(status_code=404, detail="工单不存在或无权访问")
    data = _work_order_dict(wo, include_relations=True)
    return success_response(data, request_id=request.state.request_id)


@router.post("/{work_order_id}/approve", response_model=None)
async def approve_work_order_api(
    work_order_id: int,
    req: ApprovalRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("work_order:approve")),
    db: AsyncSession = Depends(get_db),
):
    """审批通过：pending → approved"""
    wo, error = await approve_work_order(
        db, user.business_id, work_order_id, user.user_id,
        comment=req.comment, modified_params=req.modified_params,
    )
    if error:
        raise HTTPException(status_code=409, detail=error)
    data = _work_order_dict(wo, include_relations=False)
    return success_response(data, request_id=request.state.request_id)


@router.post("/{work_order_id}/reject", response_model=None)
async def reject_work_order_api(
    work_order_id: int,
    req: ApprovalRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("work_order:approve")),
    db: AsyncSession = Depends(get_db),
):
    """审批拒绝：pending → rejected"""
    wo, error = await reject_work_order(
        db, user.business_id, work_order_id, user.user_id,
        comment=req.comment,
    )
    if error:
        raise HTTPException(status_code=409, detail=error)
    data = _work_order_dict(wo, include_relations=False)
    return success_response(data, request_id=request.state.request_id)


@router.post("/{work_order_id}/cancel", response_model=None)
async def cancel_work_order_api(
    work_order_id: int,
    req: CancelRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("work_order:write")),
    db: AsyncSession = Depends(get_db),
):
    """取消工单：pending/approved → cancelled"""
    wo, error = await cancel_work_order(
        db, user.business_id, work_order_id, user.user_id,
        comment=req.comment,
    )
    if error:
        raise HTTPException(status_code=409, detail=error)
    data = _work_order_dict(wo, include_relations=False)
    return success_response(data, request_id=request.state.request_id)


@router.post("/{work_order_id}/execute", response_model=None)
async def execute_work_order_api(
    work_order_id: int,
    request: Request,
    user: CurrentUser = Depends(require_permission("work_order:approve")),
    db: AsyncSession = Depends(get_db),
):
    """开始执行：approved → executing，创建 ExecutionJob"""
    wo, error = await start_execution(db, user.business_id, work_order_id)
    if error:
        raise HTTPException(status_code=409, detail=error)
    data = _work_order_dict(wo, include_relations=True)
    return success_response(data, request_id=request.state.request_id)


@router.post("/{work_order_id}/result", response_model=None)
async def execution_result_api(
    work_order_id: int,
    req: ExecutionResult,
    request: Request,
    user: CurrentUser = Depends(require_permission("work_order:write")),
    db: AsyncSession = Depends(get_db),
):
    """回写执行结果：executing → completed/failed"""
    wo, error = await complete_execution(
        db, user.business_id, work_order_id,
        result=req.result,
        is_success=req.is_success,
        error_message=req.error_message,
    )
    if error:
        raise HTTPException(status_code=409, detail=error)
    data = _work_order_dict(wo, include_relations=True)
    return success_response(data, request_id=request.state.request_id)
