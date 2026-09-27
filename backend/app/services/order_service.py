"""订单服务层 - 状态机 + 库存联动"""
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.response import (
    BizException,
    ConflictException,
    NotFoundException,
    ValidationException,
)
from app.models import InventoryLog, Order, OrderItem, Product, SKU


def _gen_order_no() -> str:
    """生成订单号：SO + 日期 + 4位随机"""
    now = datetime.now()
    return f"SO{now.strftime('%Y%m%d')}{random.randint(1000, 9999)}"


async def _get_order_by_uuid(
    db: AsyncSession, business_id: int, order_uuid: str, for_update: bool = False
) -> Order:
    try:
        uid = UUID(order_uuid)
    except (ValueError, AttributeError):
        raise ValidationException("订单 ID 格式错误")
    stmt = select(Order).where(
        Order.uuid == uid, Order.business_id == business_id, Order.deleted_at.is_(None)
    )
    if for_update:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if order is None:
        raise NotFoundException("订单不存在")
    return order


def _order_item_dict(item: OrderItem) -> dict:
    return {
        "id": str(item.uuid) if hasattr(item, "uuid") else str(item.id),
        "sku_id": str(item.sku_id) if item.sku_id else None,
        "product_name": item.product_name,
        "sku_spec": item.sku_spec,
        "unit_price": float(item.unit_price) if item.unit_price else 0,
        "qty": item.qty,
        "subtotal": float(item.subtotal) if item.subtotal else 0,
        "discount": float(item.discount) if item.discount else 0,
    }


async def _order_dict(db: AsyncSession, order: Order, include_items: bool = False) -> dict:
    """构建订单响应"""
    # item_count
    count_stmt = select(func.count()).select_from(OrderItem).where(OrderItem.order_id == order.id)
    item_count = (await db.execute(count_stmt)).scalar_one()

    data = {
        "id": str(order.uuid),
        "order_no": order.order_no,
        "customer_id": str(order.customer_id) if order.customer_id else None,
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "total_amount": float(order.total_amount) if order.total_amount else 0,
        "discount_amount": float(order.discount_amount) if order.discount_amount else 0,
        "payable_amount": float(order.payable_amount) if order.payable_amount else 0,
        "paid_amount": float(order.paid_amount) if order.paid_amount else 0,
        "status": order.status,
        "source": order.source,
        "payment_status": order.payment_status,
        "payment_method": order.payment_method,
        "shipping_address": order.shipping_address,
        "remark": order.remark,
        "item_count": item_count,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
    }
    if include_items:
        items_stmt = select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)
        items_result = await db.execute(items_stmt)
        data["items"] = [_order_item_dict(i) for i in items_result.scalars()]
        data["status_history"] = [
            {"status": order.status, "time": order.updated_at.isoformat() if order.updated_at else None, "operator": "system"}
        ]
    return data


# ===== 创建订单（含库存扣减） =====
async def create_order(
    db: AsyncSession, business_id: int, user_id: int, req
) -> Order:
    """创建订单 - 多 SKU 明细 + 金额计算 + 库存扣减"""
    # 校验客户信息
    if not req.customer_id and not req.customer_info:
        raise ValidationException("必须提供 customer_id 或 customer_info")

    customer_name = None
    customer_phone = None
    if req.customer_info:
        customer_name = req.customer_info.name
        customer_phone = req.customer_info.phone

    # 锁定所有涉及的 SKU 并校验库存
    sku_ids = []
    for item_req in req.items:
        try:
            uid = UUID(item_req.sku_id)
            sku_ids.append(uid)
        except ValueError:
            raise ValidationException(f"SKU ID 格式错误: {item_req.sku_id}")

    # 查询 SKU（for update 锁行）
    skus = {}
    for uid in sku_ids:
        stmt = select(SKU).where(
            SKU.uuid == uid, SKU.business_id == business_id, SKU.deleted_at.is_(None)
        ).with_for_update()
        result = await db.execute(stmt)
        sku = result.scalar_one_or_none()
        if sku is None:
            raise NotFoundException(f"SKU 不存在: {uid}")
        skus[uid] = sku

    # 校验库存 + 计算金额
    total_amount = Decimal("0")
    order_items_data = []
    for item_req in req.items:
        uid = UUID(item_req.sku_id)
        sku = skus[uid]
        qty = item_req.qty
        if sku.stock_qty < qty:
            raise BizException(
                code=42201,
                message=f"库存不足：{sku.sku_code} 当前 {sku.stock_qty}，需要 {qty}",
                status_code=422,
            )
        unit_price = item_req.unit_price if item_req.unit_price is not None else sku.price
        subtotal = unit_price * qty
        total_amount += subtotal
        order_items_data.append({
            "sku": sku,
            "qty": qty,
            "unit_price": unit_price,
            "subtotal": subtotal,
        })

    # 创建订单
    order = Order(
        business_id=business_id,
        order_no=_gen_order_no(),
        customer_name=customer_name,
        customer_phone=customer_phone,
        total_amount=total_amount,
        discount_amount=Decimal("0"),
        payable_amount=total_amount,
        paid_amount=Decimal("0"),
        status="pending",
        source=req.source or "manual",
        payment_status="unpaid",
        shipping_address=req.shipping_address.model_dump() if req.shipping_address else None,
        remark=req.remark,
    )
    db.add(order)
    await db.flush()  # 拿到 order.id

    # 创建订单明细 + 扣减库存 + 写流水
    for item_data in order_items_data:
        sku = item_data["sku"]
        qty = item_data["qty"]
        unit_price = item_data["unit_price"]
        subtotal = item_data["subtotal"]

        # 查 product_name
        product_result = await db.execute(select(Product).where(Product.id == sku.product_id))
        product = product_result.scalar_one_or_none()
        product_name = product.name if product else ""
        sku_spec = sku.spec_name or ""

        item = OrderItem(
            order_id=order.id,
            business_id=business_id,
            sku_id=sku.id,
            product_name=product_name,
            sku_spec=sku_spec,
            unit_price=unit_price,
            qty=qty,
            subtotal=subtotal,
            discount=Decimal("0"),
        )
        db.add(item)

        # 扣减库存
        before_qty = sku.stock_qty
        after_qty = before_qty - qty
        sku.stock_qty = after_qty

        # 写流水
        log = InventoryLog(
            business_id=business_id,
            sku_id=sku.id,
            change_type="out",
            change_qty=-qty,
            before_qty=before_qty,
            after_qty=after_qty,
            reason=f"订单出库 {order.order_no}",
            ref_type="order",
            ref_id=order.id,
            operator_type="user",
            operator_id=user_id,
        )
        db.add(log)

    await db.commit()
    await db.refresh(order)
    return order


# ===== 订单列表 =====
async def list_orders(
    db: AsyncSession, business_id: int,
    order_no: Optional[str], status: Optional[str], source: Optional[str],
    payment_status: Optional[str], customer_keyword: Optional[str],
    start_date: Optional[str], end_date: Optional[str],
    min_amount: Optional[float], max_amount: Optional[float],
    sort_by: str, sort_order: str,
    page: int, page_size: int,
) -> Tuple[list, int]:
    stmt = select(Order).where(
        Order.business_id == business_id, Order.deleted_at.is_(None)
    )
    if order_no:
        stmt = stmt.where(Order.order_no == order_no)
    if status:
        stmt = stmt.where(Order.status == status)
    if source:
        stmt = stmt.where(Order.source == source)
    if payment_status:
        stmt = stmt.where(Order.payment_status == payment_status)
    if customer_keyword:
        like = f"%{customer_keyword}%"
        stmt = stmt.where(
            (Order.customer_name.ilike(like)) | (Order.customer_phone.ilike(like))
        )
    if start_date:
        try:
            sd = datetime.fromisoformat(start_date)
            stmt = stmt.where(Order.created_at >= sd)
        except ValueError:
            pass
    if end_date:
        try:
            ed = datetime.fromisoformat(end_date)
            stmt = stmt.where(Order.created_at <= ed)
        except ValueError:
            pass
    if min_amount is not None:
        stmt = stmt.where(Order.total_amount >= min_amount)
    if max_amount is not None:
        stmt = stmt.where(Order.total_amount <= max_amount)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    sort_map = {"created_at": Order.created_at, "total_amount": Order.total_amount}
    sort_col = sort_map.get(sort_by, Order.created_at)
    stmt = stmt.order_by(sort_col.asc() if sort_order == "asc" else sort_col.desc())

    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)

    items = []
    for order in result.scalars():
        # item_count
        cnt = (await db.execute(
            select(func.count()).select_from(OrderItem).where(OrderItem.order_id == order.id)
        )).scalar_one()
        items.append({
            "id": str(order.uuid),
            "order_no": order.order_no,
            "customer_name": order.customer_name,
            "customer_phone": order.customer_phone,
            "total_amount": float(order.total_amount) if order.total_amount else 0,
            "payable_amount": float(order.payable_amount) if order.payable_amount else 0,
            "paid_amount": float(order.paid_amount) if order.paid_amount else 0,
            "status": order.status,
            "source": order.source,
            "payment_status": order.payment_status,
            "item_count": cnt,
            "remark": order.remark,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        })
    return items, total


# ===== 订单详情 =====
async def get_order_detail(db: AsyncSession, business_id: int, order_uuid: str) -> dict:
    order = await _get_order_by_uuid(db, business_id, order_uuid)
    return await _order_dict(db, order, include_items=True)


# ===== 订单明细 =====
async def list_order_items(db: AsyncSession, business_id: int, order_uuid: str) -> list:
    order = await _get_order_by_uuid(db, business_id, order_uuid)
    stmt = select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)
    result = await db.execute(stmt)
    return [_order_item_dict(i) for i in result.scalars()]


# ===== 确认订单 =====
async def confirm_order(
    db: AsyncSession, business_id: int, user_id: int, order_uuid: str
) -> Order:
    """确认订单：pending → confirmed"""
    order = await _get_order_by_uuid(db, business_id, order_uuid, for_update=True)
    if order.status != "pending":
        raise ConflictException(f"当前订单状态({order.status})不允许确认")
    order.status = "confirmed"
    await db.commit()
    await db.refresh(order)
    return order


# ===== 支付 =====
async def pay_order(
    db: AsyncSession, business_id: int, user_id: int, order_uuid: str, req
) -> Order:
    """支付订单：pending/confirmed → paid"""
    order = await _get_order_by_uuid(db, business_id, order_uuid, for_update=True)
    if order.status not in ("pending", "confirmed"):
        raise ConflictException(f"当前订单状态({order.status})不允许支付")
    order.status = "paid"
    order.payment_status = "paid"
    order.payment_method = req.payment_method
    order.paid_amount = order.payable_amount
    order.paid_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    await db.refresh(order)
    return order


# ===== 取消订单（回滚库存） =====
async def cancel_order(
    db: AsyncSession, business_id: int, user_id: int, order_uuid: str, reason: str
) -> Order:
    """取消订单：pending/confirmed/paid → cancelled，回滚库存"""
    order = await _get_order_by_uuid(db, business_id, order_uuid, for_update=True)
    if order.status not in ("pending", "confirmed", "paid"):
        raise ConflictException(f"当前订单状态({order.status})不允许取消")

    # 查订单明细，回滚库存
    items_stmt = select(OrderItem, SKU).join(
        SKU, SKU.id == OrderItem.sku_id
    ).where(OrderItem.order_id == order.id)
    items_result = await db.execute(items_stmt)
    for item, sku in items_result:
        # 锁 SKU
        sku_obj = (await db.execute(
            select(SKU).where(SKU.id == sku.id).with_for_update()
        )).scalar_one()
        before_qty = sku_obj.stock_qty
        after_qty = before_qty + item.qty
        sku_obj.stock_qty = after_qty
        # 写回滚流水
        log = InventoryLog(
            business_id=business_id,
            sku_id=sku_obj.id,
            change_type="return",
            change_qty=item.qty,
            before_qty=before_qty,
            after_qty=after_qty,
            reason=f"订单取消回滚 {order.order_no}: {reason}",
            ref_type="order_cancel",
            ref_id=order.id,
            operator_type="user",
            operator_id=user_id,
        )
        db.add(log)

    order.status = "cancelled"
    if order.payment_status == "paid":
        order.payment_status = "refunded"
    await db.commit()
    await db.refresh(order)
    return order


# ===== 发货 =====
async def ship_order(
    db: AsyncSession, business_id: int, order_uuid: str, req
) -> Order:
    """发货：paid → shipped"""
    order = await _get_order_by_uuid(db, business_id, order_uuid, for_update=True)
    if order.status != "paid":
        raise ConflictException(f"当前订单状态({order.status})不允许发货")
    order.status = "shipped"
    # 把物流信息存到 shipping_address
    if order.shipping_address is None:
        order.shipping_address = {}
    addr = dict(order.shipping_address) if order.shipping_address else {}
    if req.shipping_company:
        addr["shipping_company"] = req.shipping_company
    if req.tracking_no:
        addr["tracking_no"] = req.tracking_no
    if req.remark:
        addr["ship_remark"] = req.remark
    order.shipping_address = addr
    await db.commit()
    await db.refresh(order)
    return order


# ===== 完成 =====
async def complete_order(
    db: AsyncSession, business_id: int, order_uuid: str
) -> Order:
    """完成订单：shipped → completed"""
    order = await _get_order_by_uuid(db, business_id, order_uuid, for_update=True)
    if order.status != "shipped":
        raise ConflictException(f"当前订单状态({order.status})不允许完成")
    order.status = "completed"
    await db.commit()
    await db.refresh(order)
    return order


# ===== 退款（简化：直接执行 + 回滚库存） =====
async def refund_order(
    db: AsyncSession, business_id: int, user_id: int, order_uuid: str, req
) -> dict:
    """退款：paid/shipped/completed → refunded"""
    order = await _get_order_by_uuid(db, business_id, order_uuid, for_update=True)
    if order.status not in ("paid", "shipped", "completed"):
        raise ConflictException(f"当前订单状态({order.status})不允许退款")

    refund_amount = req.refund_amount
    if refund_amount > order.paid_amount:
        raise BizException(
            code=42201,
            message=f"退款金额({refund_amount})大于实付金额({order.paid_amount})",
            status_code=422,
        )

    # 部分退款不回滚库存，全额退款回滚
    if req.refund_type == "full":
        items_stmt = select(OrderItem, SKU).join(
            SKU, SKU.id == OrderItem.sku_id
        ).where(OrderItem.order_id == order.id)
        items_result = await db.execute(items_stmt)
        for item, sku in items_result:
            sku_obj = (await db.execute(
                select(SKU).where(SKU.id == sku.id).with_for_update()
            )).scalar_one()
            before_qty = sku_obj.stock_qty
            after_qty = before_qty + item.qty
            sku_obj.stock_qty = after_qty
            log = InventoryLog(
                business_id=business_id,
                sku_id=sku_obj.id,
                change_type="return",
                change_qty=item.qty,
                before_qty=before_qty,
                after_qty=after_qty,
                reason=f"订单退款回滚 {order.order_no}: {req.refund_reason}",
                ref_type="order_refund",
                ref_id=order.id,
                operator_type="user",
                operator_id=user_id,
            )
            db.add(log)

    order.status = "refunded"
    order.payment_status = "refunded"
    await db.commit()

    return {
        "work_order_id": None,
        "order_id": str(order.uuid),
        "order_no": order.order_no,
        "refund_amount": float(refund_amount),
        "refund_reason": req.refund_reason,
        "refund_type": req.refund_type,
        "status": "completed",
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    }


# ===== 订单统计 =====
async def get_order_stats(
    db: AsyncSession, business_id: int, period: str
) -> dict:
    """订单统计"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7d":
        start = now - timedelta(days=7)
    elif period == "30d":
        start = now - timedelta(days=30)
    elif period == "90d":
        start = now - timedelta(days=90)
    else:
        start = now - timedelta(days=7)

    # 汇总
    summary_stmt = select(
        func.count(),
        func.coalesce(func.sum(Order.total_amount), 0),
        func.count().filter(Order.status == "completed"),
        func.count().filter(Order.status == "cancelled"),
        func.count().filter(Order.status == "refunded"),
    ).where(
        Order.business_id == business_id,
        Order.deleted_at.is_(None),
        Order.created_at >= start,
    )
    result = await db.execute(summary_stmt)
    total_orders, total_amount, completed, cancelled, refunded = result.one()
    avg_order = float(total_amount) / total_orders if total_orders > 0 else 0

    return {
        "period": period,
        "summary": {
            "total_orders": total_orders,
            "total_amount": float(total_amount),
            "avg_order_value": round(avg_order, 2),
            "completed_count": completed,
            "cancelled_count": cancelled,
            "refunded_count": refunded,
        },
        "trend": [],
    }
