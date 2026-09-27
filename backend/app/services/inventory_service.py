"""库存服务层 - 库存查询/调整/流水/预警/批次/盘点"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.response import (
    NotFoundException,
    ValidationException,
)
from app.models import (
    InventoryBatch,
    InventoryLog,
    Order,
    OrderItem,
    Product,
    SKU,
    User,
)


async def _get_sku_by_uuid(
    db: AsyncSession, business_id: int, sku_uuid: str, for_update: bool = False
) -> SKU:
    """按 UUID 查询 SKU"""
    try:
        uid = UUID(sku_uuid)
    except (ValueError, AttributeError):
        raise ValidationException("SKU ID 格式错误")
    stmt = select(SKU).where(
        SKU.uuid == uid, SKU.business_id == business_id, SKU.deleted_at.is_(None)
    )
    if for_update:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    sku = result.scalar_one_or_none()
    if sku is None:
        raise NotFoundException("SKU 不存在")
    return sku


def _calc_stock_status(stock_qty: int, safety_stock: int, min_stock: int) -> str:
    """计算库存状态"""
    if stock_qty <= 0:
        return "out_of_stock"
    if min_stock > 0 and stock_qty <= min_stock:
        return "low"
    if safety_stock > 0 and stock_qty <= safety_stock:
        return "low"
    return "normal"


def _calc_alert_level(stock_qty: int, safety_stock: int, min_stock: int) -> Optional[str]:
    """计算预警级别（red/orange/yellow），正常返回 None"""
    if stock_qty <= 0:
        return "red"
    if min_stock > 0 and stock_qty <= min_stock:
        return "orange"
    if safety_stock > 0 and stock_qty <= safety_stock:
        return "yellow"
    return None


async def _avg_daily_sales(db: AsyncSession, sku_id: int, days: int = 30) -> float:
    """计算近 N 天日均销量"""
    start = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = select(func.coalesce(func.sum(OrderItem.qty), 0)).join(
        Order, Order.id == OrderItem.order_id
    ).where(
        OrderItem.sku_id == sku_id,
        Order.deleted_at.is_(None),
        Order.status.notin_(["cancelled"]),
        Order.created_at >= start,
    )
    total = (await db.execute(stmt)).scalar_one()
    return float(total) / days if days > 0 else 0.0


# ===== 5.1 库存列表 =====
async def list_inventory(
    db: AsyncSession, business_id: int,
    keyword: Optional[str], category: Optional[str], sku_code: Optional[str],
    stock_status: Optional[str], sort_by: str, sort_order: str,
    page: int, page_size: int,
) -> Tuple[list, int]:
    """库存列表"""
    stmt = select(SKU, Product).join(
        Product, Product.id == SKU.product_id
    ).where(
        SKU.business_id == business_id,
        SKU.deleted_at.is_(None),
        Product.deleted_at.is_(None),
    )
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            (Product.name.ilike(like)) | (SKU.sku_code.ilike(like))
        )
    if category:
        stmt = stmt.where(Product.category == category)
    if sku_code:
        stmt = stmt.where(SKU.sku_code == sku_code)

    # 库存状态筛选
    if stock_status == "out_of_stock":
        stmt = stmt.where(SKU.stock_qty <= 0)
    elif stock_status == "low":
        stmt = stmt.where(
            (SKU.safety_stock > 0) & (SKU.stock_qty <= SKU.safety_stock)
        )

    # 排序
    sort_map = {"stock_qty": SKU.stock_qty, "updated_at": SKU.updated_at, "price": SKU.price}
    sort_col = sort_map.get(sort_by, SKU.stock_qty)
    stmt = stmt.order_by(sort_col.asc() if sort_order == "asc" else sort_col.desc())

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)

    items = []
    for sku, product in result:
        status = _calc_stock_status(sku.stock_qty, sku.safety_stock, sku.min_stock)
        items.append({
            "sku_id": str(sku.uuid),
            "product_id": str(product.uuid),
            "sku_code": sku.sku_code,
            "product_name": product.name,
            "spec_name": sku.spec_name,
            "category": product.category,
            "price": float(sku.price) if sku.price else 0,
            "stock_qty": sku.stock_qty,
            "safety_stock": sku.safety_stock,
            "min_stock": sku.min_stock,
            "stock_status": status,
            "updated_at": sku.updated_at.isoformat() if sku.updated_at else None,
        })
    return items, total


# ===== 5.2 库存详情 =====
async def get_inventory_detail(
    db: AsyncSession, business_id: int, sku_uuid: str
) -> dict:
    """库存详情"""
    sku = await _get_sku_by_uuid(db, business_id, sku_uuid)
    product_result = await db.execute(select(Product).where(Product.id == sku.product_id))
    product = product_result.scalar_one_or_none()

    # 最近入库时间
    last_in_stmt = select(InventoryLog.created_at).where(
        InventoryLog.sku_id == sku.id,
        InventoryLog.change_type == "in",
    ).order_by(InventoryLog.created_at.desc()).limit(1)
    last_restocked = (await db.execute(last_in_stmt)).scalar_one_or_none()

    # 最近出库
    last_out_stmt = select(InventoryLog.created_at).where(
        InventoryLog.sku_id == sku.id,
        InventoryLog.change_type == "out",
    ).order_by(InventoryLog.created_at.desc()).limit(1)
    last_out = (await db.execute(last_out_stmt)).scalar_one_or_none()

    avg_sales = await _avg_daily_sales(db, sku.id)
    days_of_stock = round(sku.stock_qty / avg_sales, 1) if avg_sales > 0 else None

    return {
        "sku_id": str(sku.uuid),
        "product_id": str(product.uuid) if product else None,
        "sku_code": sku.sku_code,
        "product_name": product.name if product else None,
        "spec_name": sku.spec_name,
        "category": product.category if product else None,
        "price": float(sku.price) if sku.price else 0,
        "cost_price": float(sku.cost_price) if sku.cost_price else 0,
        "stock_qty": sku.stock_qty,
        "safety_stock": sku.safety_stock,
        "min_stock": sku.min_stock,
        "stock_status": _calc_stock_status(sku.stock_qty, sku.safety_stock, sku.min_stock),
        "last_restocked_at": last_restocked.isoformat() if last_restocked else None,
        "last_out_at": last_out.isoformat() if last_out else None,
        "avg_daily_sales": round(avg_sales, 2),
        "days_of_stock": days_of_stock,
        "updated_at": sku.updated_at.isoformat() if sku.updated_at else None,
    }


# ===== 5.3 库存调整 =====
async def adjust_inventory(
    db: AsyncSession, business_id: int, user_id: int, req
) -> dict:
    """库存调整 - 写流水 + 更新库存 + 入库创建批次"""
    sku = await _get_sku_by_uuid(db, business_id, req.sku_id, for_update=True)

    before_qty = sku.stock_qty
    change_qty = req.change_qty

    # 出库数量必须为负；入库为正；adjust 可正可负
    if req.change_type == "out" and change_qty > 0:
        change_qty = -change_qty
    if req.change_type == "in" and change_qty < 0:
        change_qty = -change_qty

    after_qty = before_qty + change_qty
    if after_qty < 0:
        from app.api.response import BizException
        raise BizException(code=42201, message="库存不足，出库数量超过当前库存", status_code=422)

    # 写流水
    log = InventoryLog(
        business_id=business_id,
        sku_id=sku.id,
        change_type=req.change_type,
        change_qty=change_qty,
        before_qty=before_qty,
        after_qty=after_qty,
        reason=req.reason,
        ref_type="manual" if req.change_type != "adjust" else "adjust",
        operator_type="user",
        operator_id=user_id,
    )
    db.add(log)

    # 更新库存
    sku.stock_qty = after_qty

    # 入库且有批次号：创建批次
    if req.change_type == "in" and req.batch_no:
        # 校验批次号唯一
        existing = await db.execute(
            select(InventoryBatch.id).where(InventoryBatch.batch_no == req.batch_no)
        )
        if existing.first() is not None:
            raise ValidationException("批次号已存在")
        today = date.today()
        batch = InventoryBatch(
            business_id=business_id,
            sku_id=sku.id,
            batch_no=req.batch_no,
            in_qty=change_qty,
            remaining_qty=change_qty,
            in_date=today,
            expire_date=req.expire_date,
            status="active",
        )
        db.add(batch)

    await db.commit()
    await db.refresh(log)

    return {
        "log_id": str(log.uuid) if hasattr(log, "uuid") else None,
        "sku_id": req.sku_id,
        "change_type": req.change_type,
        "change_qty": change_qty,
        "before_qty": before_qty,
        "after_qty": after_qty,
        "reason": req.reason,
        "status": "completed",
        "work_order_id": None,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


# ===== 5.4 库存流水 =====
async def list_inventory_logs(
    db: AsyncSession, business_id: int,
    sku_id: Optional[str], change_type: Optional[str],
    operator_type: Optional[str],
    start_date: Optional[str], end_date: Optional[str],
    page: int, page_size: int,
) -> Tuple[list, int]:
    """库存流水"""
    stmt = select(InventoryLog, SKU, Product).join(
        SKU, SKU.id == InventoryLog.sku_id
    ).join(
        Product, Product.id == SKU.product_id
    ).where(InventoryLog.business_id == business_id)

    if sku_id:
        try:
            uid = UUID(sku_id)
            stmt = stmt.where(SKU.uuid == uid)
        except ValueError:
            pass
    if change_type:
        stmt = stmt.where(InventoryLog.change_type == change_type)
    if operator_type:
        stmt = stmt.where(InventoryLog.operator_type == operator_type)
    if start_date:
        try:
            sd = datetime.fromisoformat(start_date)
            stmt = stmt.where(InventoryLog.created_at >= sd)
        except ValueError:
            pass
    if end_date:
        try:
            ed = datetime.fromisoformat(end_date)
            stmt = stmt.where(InventoryLog.created_at <= ed)
        except ValueError:
            pass

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(InventoryLog.created_at.desc())
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)

    items = []
    for log, sku, product in result:
        items.append({
            "id": str(log.uuid) if hasattr(log, "uuid") else str(log.id),
            "sku_id": str(sku.uuid),
            "sku_code": sku.sku_code,
            "product_name": product.name if product else None,
            "change_type": log.change_type,
            "change_qty": log.change_qty,
            "before_qty": log.before_qty,
            "after_qty": log.after_qty,
            "reason": log.reason,
            "ref_type": log.ref_type,
            "ref_id": str(log.ref_id) if log.ref_id else None,
            "operator_type": log.operator_type,
            "operator_name": None,  # 简化：不查 User
            "created_at": log.created_at.isoformat() if log.created_at else None,
        })
    return items, total


# ===== 5.5 库存预警 =====
async def list_inventory_alerts(
    db: AsyncSession, business_id: int,
    level: Optional[str], category: Optional[str],
    page: int, page_size: int,
) -> Tuple[list, int, dict]:
    """库存预警列表 + 汇总"""
    stmt = select(SKU, Product).join(
        Product, Product.id == SKU.product_id
    ).where(
        SKU.business_id == business_id,
        SKU.deleted_at.is_(None),
        Product.deleted_at.is_(None),
        # 至少有一种预警：stock_qty <= safety_stock (safety_stock>0) 或 stock_qty <= 0
        (
            ((SKU.safety_stock > 0) & (SKU.stock_qty <= SKU.safety_stock))
            | (SKU.stock_qty <= 0)
        ),
    )
    if category:
        stmt = stmt.where(Product.category == category)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # 汇总（不分页）
    summary = {"red_count": 0, "orange_count": 0, "yellow_count": 0}
    all_alerts_stmt = select(SKU).where(
        SKU.business_id == business_id,
        SKU.deleted_at.is_(None),
        ((SKU.safety_stock > 0) & (SKU.stock_qty <= SKU.safety_stock))
        | (SKU.stock_qty <= 0),
    )
    all_result = await db.execute(all_alerts_stmt)
    for sku in all_result.scalars():
        lv = _calc_alert_level(sku.stock_qty, sku.safety_stock, sku.min_stock)
        if lv == "red":
            summary["red_count"] += 1
        elif lv == "orange":
            summary["orange_count"] += 1
        elif lv == "yellow":
            summary["yellow_count"] += 1

    # 级别筛选
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size).order_by(SKU.stock_qty.asc())
    result = await db.execute(stmt)

    items = []
    for sku, product in result:
        lv = _calc_alert_level(sku.stock_qty, sku.safety_stock, sku.min_stock)
        if level and lv != level:
            continue
        avg_sales = await _avg_daily_sales(db, sku.id)
        days_of_stock = round(sku.stock_qty / avg_sales, 1) if avg_sales > 0 else None
        items.append({
            "sku_id": str(sku.uuid),
            "sku_code": sku.sku_code,
            "product_name": product.name if product else None,
            "spec_name": sku.spec_name,
            "stock_qty": sku.stock_qty,
            "safety_stock": sku.safety_stock,
            "min_stock": sku.min_stock,
            "alert_level": lv,
            "avg_daily_sales": round(avg_sales, 2),
            "days_of_stock": days_of_stock,
        })
    return items, total, summary


# ===== 5.6 临期商品 =====
async def list_expiring(
    db: AsyncSession, business_id: int,
    days: int, category: Optional[str],
    page: int, page_size: int,
) -> Tuple[list, int]:
    """临期商品列表（基于批次 expire_date）"""
    threshold_date = date.today() + timedelta(days=days)
    stmt = select(InventoryBatch, SKU, Product).join(
        SKU, SKU.id == InventoryBatch.sku_id
    ).join(
        Product, Product.id == SKU.product_id
    ).where(
        InventoryBatch.business_id == business_id,
        InventoryBatch.status == "active",
        InventoryBatch.remaining_qty > 0,
        InventoryBatch.expire_date.is_not(None),
        InventoryBatch.expire_date <= threshold_date,
    )
    if category:
        stmt = stmt.where(Product.category == category)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(InventoryBatch.expire_date.asc())
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)

    today = date.today()
    items = []
    for batch, sku, product in result:
        days_remaining = (batch.expire_date - today).days if batch.expire_date else None
        items.append({
            "sku_id": str(sku.uuid),
            "sku_code": sku.sku_code,
            "product_name": product.name if product else None,
            "batch_no": batch.batch_no,
            "remaining_qty": batch.remaining_qty,
            "expire_date": batch.expire_date.isoformat() if batch.expire_date else None,
            "days_remaining": days_remaining,
            "in_date": batch.in_date.isoformat() if batch.in_date else None,
            "status": batch.status,
        })
    return items, total


# ===== 5.7 盘点 =====
async def stocktake(
    db: AsyncSession, business_id: int, user_id: int, req
) -> dict:
    """盘点 - 对比系统量，生成差异流水"""
    diff_items = []
    for item in req.items:
        sku = await _get_sku_by_uuid(db, business_id, item.sku_id, for_update=True)
        system_qty = sku.stock_qty
        actual_qty = item.actual_qty
        diff = actual_qty - system_qty
        if diff == 0:
            continue
        before_qty = sku.stock_qty
        after_qty = actual_qty
        # 写调整流水
        log = InventoryLog(
            business_id=business_id,
            sku_id=sku.id,
            change_type="check",
            change_qty=diff,
            before_qty=before_qty,
            after_qty=after_qty,
            reason=req.remark or "盘点差异调整",
            ref_type="stocktake",
            operator_type="user",
            operator_id=user_id,
        )
        db.add(log)
        sku.stock_qty = after_qty
        diff_items.append({
            "sku_id": item.sku_id,
            "system_qty": system_qty,
            "actual_qty": actual_qty,
            "diff_qty": diff,
        })

    await db.commit()
    import uuid as uuid_lib
    return {
        "stocktake_id": str(uuid_lib.uuid4()),
        "total_items": len(req.items),
        "diff_items": len(diff_items),
        "diff_summary": diff_items,
        "work_order_id": None,
        "status": "completed" if diff_items else "completed",
    }


# ===== 5.8 批次列表 =====
async def list_batches(
    db: AsyncSession, business_id: int,
    sku_id: Optional[str], status: Optional[str],
    expire_before: Optional[str],
    page: int, page_size: int,
) -> Tuple[list, int]:
    """批次列表"""
    stmt = select(InventoryBatch, SKU, Product).join(
        SKU, SKU.id == InventoryBatch.sku_id
    ).join(
        Product, Product.id == SKU.product_id
    ).where(InventoryBatch.business_id == business_id)

    if sku_id:
        try:
            uid = UUID(sku_id)
            stmt = stmt.where(SKU.uuid == uid)
        except ValueError:
            pass
    if status:
        stmt = stmt.where(InventoryBatch.status == status)
    if expire_before:
        try:
            ed = date.fromisoformat(expire_before)
            stmt = stmt.where(InventoryBatch.expire_date <= ed)
        except ValueError:
            pass

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(InventoryBatch.created_at.desc())
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)

    items = []
    for batch, sku, product in result:
        items.append({
            "id": str(batch.uuid) if hasattr(batch, "uuid") else str(batch.id),
            "sku_id": str(sku.uuid),
            "sku_code": sku.sku_code,
            "product_name": product.name if product else None,
            "batch_no": batch.batch_no,
            "in_qty": batch.in_qty,
            "remaining_qty": batch.remaining_qty,
            "in_date": batch.in_date.isoformat() if batch.in_date else None,
            "expire_date": batch.expire_date.isoformat() if batch.expire_date else None,
            "status": batch.status,
            "supplier": None,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
        })
    return items, total
