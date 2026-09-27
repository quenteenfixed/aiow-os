"""订单 API 路由"""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_pagination, require_permission
from app.api.response import success_response
from app.database import get_db
from app.schemas.order import (
    CancelOrderRequest,
    CreateOrderRequest,
    PayOrderRequest,
    RefundRequest,
    ShipOrderRequest,
)
from app.services.order_service import (
    cancel_order,
    complete_order,
    confirm_order,
    create_order,
    get_order_detail,
    get_order_stats,
    list_order_items,
    list_orders,
    pay_order,
    refund_order,
    ship_order,
    _order_dict,
)

router = APIRouter()


@router.get("/stats", response_model=None)
async def stats_api(
    request: Request,
    period: str = Query("7d", pattern="^(today|7d|30d|90d)$"),
    user: CurrentUser = Depends(require_permission("order:read")),
    db: AsyncSession = Depends(get_db),
):
    """订单统计"""
    data = await get_order_stats(db, user.business_id, period)
    return success_response(data, request_id=request.state.request_id)


@router.get("", response_model=None)
async def list_orders_api(
    request: Request,
    order_no: str = Query(None),
    status: str = Query(None),
    source: str = Query(None),
    payment_status: str = Query(None),
    customer_keyword: str = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None),
    min_amount: float = Query(None, ge=0),
    max_amount: float = Query(None, ge=0),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    pagination: Depends = Depends(get_pagination),
    user: CurrentUser = Depends(require_permission("order:read")),
    db: AsyncSession = Depends(get_db),
):
    """订单列表"""
    items, total = await list_orders(
        db, user.business_id, order_no, status, source, payment_status,
        customer_keyword, start_date, end_date, min_amount, max_amount,
        sort_by, sort_order, pagination.page, pagination.page_size,
    )
    total_pages = (total + pagination.page_size - 1) // pagination.page_size if pagination.page_size > 0 else 0
    data = {"items": items, "total": total, "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages}
    return success_response(data, request_id=request.state.request_id)


@router.post("", response_model=None)
async def create_order_api(
    req: CreateOrderRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("order:write")),
    db: AsyncSession = Depends(get_db),
):
    """创建订单（多 SKU + 库存扣减）"""
    order = await create_order(db, user.business_id, user.user_id, req)
    data = await _order_dict(db, order, include_items=True)
    return success_response(data, request_id=request.state.request_id)


@router.get("/{order_id}/items", response_model=None)
async def list_items_api(
    order_id: str,
    request: Request,
    user: CurrentUser = Depends(require_permission("order:read")),
    db: AsyncSession = Depends(get_db),
):
    """订单明细"""
    items = await list_order_items(db, user.business_id, order_id)
    return success_response(items, request_id=request.state.request_id)


@router.get("/{order_id}", response_model=None)
async def get_order_api(
    order_id: str,
    request: Request,
    user: CurrentUser = Depends(require_permission("order:read")),
    db: AsyncSession = Depends(get_db),
):
    """订单详情"""
    data = await get_order_detail(db, user.business_id, order_id)
    return success_response(data, request_id=request.state.request_id)


@router.post("/{order_id}/confirm", response_model=None)
async def confirm_api(
    order_id: str,
    request: Request,
    user: CurrentUser = Depends(require_permission("order:write")),
    db: AsyncSession = Depends(get_db),
):
    """确认订单：pending → confirmed"""
    order = await confirm_order(db, user.business_id, user.user_id, order_id)
    data = await _order_dict(db, order, include_items=False)
    return success_response(data, request_id=request.state.request_id)


@router.post("/{order_id}/pay", response_model=None)
async def pay_api(
    order_id: str,
    req: PayOrderRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("order:write")),
    db: AsyncSession = Depends(get_db),
):
    """支付订单"""
    order = await pay_order(db, user.business_id, user.user_id, order_id, req)
    data = await _order_dict(db, order, include_items=False)
    return success_response(data, request_id=request.state.request_id)


@router.post("/{order_id}/cancel", response_model=None)
async def cancel_api(
    order_id: str,
    req: CancelOrderRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("order:write")),
    db: AsyncSession = Depends(get_db),
):
    """取消订单（回滚库存）"""
    order = await cancel_order(db, user.business_id, user.user_id, order_id, req.reason)
    data = {
        "id": str(order.uuid),
        "order_no": order.order_no,
        "status": order.status,
        "cancel_reason": req.reason,
        "cancelled_at": order.updated_at.isoformat() if order.updated_at else None,
    }
    return success_response(data, request_id=request.state.request_id)


@router.post("/{order_id}/ship", response_model=None)
async def ship_api(
    order_id: str,
    req: ShipOrderRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("order:write")),
    db: AsyncSession = Depends(get_db),
):
    """发货"""
    order = await ship_order(db, user.business_id, order_id, req)
    addr = order.shipping_address or {}
    data = {
        "id": str(order.uuid),
        "order_no": order.order_no,
        "status": order.status,
        "shipping_company": addr.get("shipping_company"),
        "tracking_no": addr.get("tracking_no"),
        "shipped_at": order.updated_at.isoformat() if order.updated_at else None,
    }
    return success_response(data, request_id=request.state.request_id)


@router.post("/{order_id}/complete", response_model=None)
async def complete_api(
    order_id: str,
    request: Request,
    user: CurrentUser = Depends(require_permission("order:write")),
    db: AsyncSession = Depends(get_db),
):
    """完成订单"""
    order = await complete_order(db, user.business_id, order_id)
    data = {"id": str(order.uuid), "order_no": order.order_no, "status": order.status}
    return success_response(data, request_id=request.state.request_id)


@router.post("/{order_id}/refund", response_model=None)
async def refund_api(
    order_id: str,
    req: RefundRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("order:write")),
    db: AsyncSession = Depends(get_db),
):
    """退款（全额回滚库存）"""
    data = await refund_order(db, user.business_id, user.user_id, order_id, req)
    return success_response(data, request_id=request.state.request_id)
