"""客户档案服务 - CRUD / 分级 / 标签 / 统计"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.response import (
    ConflictException,
    NotFoundException,
    ValidationException,
)
from app.models import Customer, Order


# ===== 等级阈值（基于累计消费金额，单位元）=====
LEVEL_THRESHOLDS = [
    (Decimal("10000"), "svip"),
    (Decimal("1000"), "vip"),
    (Decimal("0"), "normal"),
]


def _calc_level(total_amount: Decimal) -> str:
    """按累计消费自动计算等级"""
    for threshold, level in LEVEL_THRESHOLDS:
        if total_amount >= threshold:
            return level
    return "normal"


async def _get_customer_by_uuid(
    db: AsyncSession, business_id: int, customer_uuid: str, for_update: bool = False
) -> Customer:
    """按 UUID 查询客户（含商户隔离 + 软删除过滤）"""
    try:
        uid = UUID(customer_uuid)
    except (ValueError, AttributeError):
        raise ValidationException("客户 ID 格式错误")

    stmt = select(Customer).where(
        Customer.uuid == uid,
        Customer.business_id == business_id,
        Customer.deleted_at.is_(None),
    )
    if for_update:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    customer = result.scalar_one_or_none()
    if customer is None:
        raise NotFoundException("客户不存在")
    return customer


def _customer_dict(customer: Customer, include_orders: bool = False, orders_data: Optional[list] = None) -> dict:
    """构建客户响应数据"""
    data = {
        "id": str(customer.uuid),
        "name": customer.name,
        "phone": customer.phone,
        "email": customer.email,
        "avatar": customer.avatar,
        "level": customer.level,
        "tags": customer.tags or [],
        "total_orders": customer.total_orders,
        "total_amount": float(customer.total_amount) if customer.total_amount is not None else 0.0,
        "last_order_at": customer.last_order_at.isoformat() if customer.last_order_at else None,
        "created_at": customer.created_at.isoformat() if customer.created_at else None,
        "updated_at": customer.updated_at.isoformat() if customer.updated_at else None,
    }
    if include_orders:
        data["orders"] = orders_data or []
    return data


def _order_brief(order: Order) -> dict:
    """订单简要信息（用于客户详情的订单历史）"""
    return {
        "id": str(order.uuid),
        "order_no": order.order_no,
        "status": order.status,
        "total_amount": float(order.total_amount) if order.total_amount is not None else 0.0,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }


# ===== CRUD =====
async def list_customers(
    db: AsyncSession,
    business_id: int,
    keyword: Optional[str],
    level: Optional[str],
    tag: Optional[str],
    sort_by: str,
    sort_order: str,
    page: int,
    page_size: int,
) -> Tuple[list, int]:
    """客户列表（关键字搜 name/phone/email；level/tag 过滤）"""
    stmt = select(Customer).where(
        Customer.business_id == business_id,
        Customer.deleted_at.is_(None),
    )
    if keyword:
        kw = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                Customer.name.ilike(kw),
                Customer.phone.ilike(kw),
                Customer.email.ilike(kw),
            )
        )
    if level:
        stmt = stmt.where(Customer.level == level)
    if tag:
        # ARRAY 包含查询
        stmt = stmt.where(Customer.tags.any(tag))

    # 排序
    sort_col = {
        "created_at": Customer.created_at,
        "total_amount": Customer.total_amount,
        "total_orders": Customer.total_orders,
        "last_order_at": Customer.last_order_at,
    }.get(sort_by, Customer.created_at)
    stmt = stmt.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())

    # 计数
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # 分页
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    items = [_customer_dict(c) for c in result.scalars()]
    return items, total


async def create_customer(
    db: AsyncSession, business_id: int, req
) -> Customer:
    """创建客户档案（同商户 phone 唯一）"""
    # phone 唯一性校验（同商户 + 未删除）
    if req.phone:
        existing = await db.execute(
            select(Customer.id).where(
                Customer.business_id == business_id,
                Customer.phone == req.phone,
                Customer.deleted_at.is_(None),
            )
        )
        if existing.first() is not None:
            raise ConflictException(f"手机号 {req.phone} 已存在客户档案")

    customer = Customer(
        business_id=business_id,
        name=req.name,
        phone=req.phone,
        email=req.email,
        avatar=req.avatar,
        level=req.level or "normal",
        tags=req.tags or [],
        total_orders=0,
        total_amount=Decimal("0"),
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


async def get_customer_detail(
    db: AsyncSession, business_id: int, customer_uuid: str
) -> Tuple[Customer, list]:
    """客户详情（含最近订单历史）"""
    customer = await _get_customer_by_uuid(db, business_id, customer_uuid)
    # 查询客户最近 50 单（按时间倒序）
    orders_stmt = (
        select(Order)
        .where(Order.customer_id == customer.id, Order.deleted_at.is_(None))
        .order_by(Order.created_at.desc())
        .limit(50)
    )
    orders = (await db.execute(orders_stmt)).scalars().all()
    return customer, [_order_brief(o) for o in orders]


async def update_customer(
    db: AsyncSession, business_id: int, customer_uuid: str, req
) -> Customer:
    """更新客户档案基础信息"""
    customer = await _get_customer_by_uuid(db, business_id, customer_uuid, for_update=True)

    # phone 唯一性校验（如果改了 phone）
    if req.phone is not None and req.phone != customer.phone:
        existing = await db.execute(
            select(Customer.id).where(
                Customer.business_id == business_id,
                Customer.phone == req.phone,
                Customer.deleted_at.is_(None),
                Customer.id != customer.id,
            )
        )
        if existing.first() is not None:
            raise ConflictException(f"手机号 {req.phone} 已被其他客户占用")

    update_fields = ["name", "phone", "email", "avatar"]
    changed = False
    for field in update_fields:
        val = getattr(req, field, None)
        if val is not None:
            setattr(customer, field, val)
            changed = True
    if not changed:
        raise ValidationException("至少需要提供一个更新字段")

    await db.commit()
    await db.refresh(customer)
    return customer


async def delete_customer(
    db: AsyncSession, business_id: int, customer_uuid: str
) -> Customer:
    """软删除客户档案"""
    customer = await _get_customer_by_uuid(db, business_id, customer_uuid, for_update=True)
    customer.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    await db.refresh(customer)
    return customer


# ===== 标签管理 =====
async def replace_tags(
    db: AsyncSession, business_id: int, customer_uuid: str, tags: List[str]
) -> Customer:
    """批量替换客户标签"""
    customer = await _get_customer_by_uuid(db, business_id, customer_uuid, for_update=True)
    # 去重 + 限制 20 个
    unique_tags = list(dict.fromkeys(tags))[:20]
    customer.tags = unique_tags
    await db.commit()
    await db.refresh(customer)
    return customer


async def add_tag(
    db: AsyncSession, business_id: int, customer_uuid: str, tag: str
) -> Customer:
    """新增单个标签（已存在则忽略）"""
    customer = await _get_customer_by_uuid(db, business_id, customer_uuid, for_update=True)
    current = list(customer.tags or [])
    if tag not in current:
        if len(current) >= 20:
            raise ValidationException("客户标签数量已达上限(20)")
        current.append(tag)
        customer.tags = current
        await db.commit()
        await db.refresh(customer)
    return customer


async def remove_tag(
    db: AsyncSession, business_id: int, customer_uuid: str, tag: str
) -> Customer:
    """移除单个标签"""
    customer = await _get_customer_by_uuid(db, business_id, customer_uuid, for_update=True)
    current = list(customer.tags or [])
    if tag not in current:
        raise NotFoundException(f"标签 {tag} 不存在")
    current.remove(tag)
    customer.tags = current
    await db.commit()
    await db.refresh(customer)
    return customer


# ===== 等级管理 =====
async def set_level(
    db: AsyncSession, business_id: int, customer_uuid: str, level: str
) -> Customer:
    """手动调整客户等级（管理员覆盖自动计算）"""
    customer = await _get_customer_by_uuid(db, business_id, customer_uuid, for_update=True)
    customer.level = level
    await db.commit()
    await db.refresh(customer)
    return customer


async def recalc_levels(db: AsyncSession, business_id: int) -> dict:
    """批量重算所有客户等级（基于 total_amount）"""
    stmt = select(Customer).where(
        Customer.business_id == business_id,
        Customer.deleted_at.is_(None),
    )
    customers = (await db.execute(stmt)).scalars().all()
    changed = 0
    for c in customers:
        new_level = _calc_level(c.total_amount or Decimal("0"))
        if new_level != c.level:
            c.level = new_level
            changed += 1
    await db.commit()
    return {"total": len(customers), "changed": changed}


# ===== 统计 =====
async def get_customer_stats(
    db: AsyncSession, business_id: int
) -> dict:
    """客户统计：按等级分布、总数、累计消费、平均客单"""
    # 总数 + 累计消费
    base_stmt = select(
        func.count(Customer.id),
        func.coalesce(func.sum(Customer.total_amount), 0),
        func.coalesce(func.sum(Customer.total_orders), 0),
    ).where(
        Customer.business_id == business_id,
        Customer.deleted_at.is_(None),
    )
    total_count, total_amount, total_orders = (await db.execute(base_stmt)).one()

    # 等级分布
    level_stmt = (
        select(Customer.level, func.count(Customer.id))
        .where(
            Customer.business_id == business_id,
            Customer.deleted_at.is_(None),
        )
        .group_by(Customer.level)
    )
    level_dist_rows = (await db.execute(level_stmt)).all()
    level_distribution = {row[0]: row[1] for row in level_dist_rows}

    # 各等级补 0
    for lvl in ["normal", "vip", "svip"]:
        level_distribution.setdefault(lvl, 0)

    avg_amount = (float(total_amount) / total_count) if total_count else 0.0
    avg_orders = (int(total_orders) / total_count) if total_count else 0.0

    return {
        "total_customers": int(total_count),
        "total_amount": float(total_amount),
        "total_orders": int(total_orders),
        "avg_customer_amount": round(avg_amount, 2),
        "avg_customer_orders": round(avg_orders, 2),
        "level_distribution": level_distribution,
    }
