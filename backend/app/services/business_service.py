"""商业实体服务层 - 业务逻辑"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.response import (
    ConflictException,
    NotFoundException,
    PermissionException,
    ValidationException,
)
from app.core.rbac import Role
from app.models import (
    Agent,
    Alert,
    Business,
    Order,
    Product,
    SKU,
    UserBusinessRole,
    WorkOrder,
)

# 默认经营参数
DEFAULT_CONFIG = {
    "business_hours": "24/7",
    "min_profit_rate": 0.2,
    "inventory_alert_threshold": 10,
    "price_adjust_approval_threshold": 0.1,
    "daily_loss_limit": 500.00,
    "auto_approve_low_risk": False,
    "notify_config": {"email": True, "sms": False, "in_app": True},
}


async def _check_membership(
    db: AsyncSession, user_id: int, business_id: int
) -> Optional[str]:
    """校验用户是否为某商户成员，返回 role；非成员返回 None"""
    stmt = select(UserBusinessRole.role).where(
        UserBusinessRole.user_id == user_id,
        UserBusinessRole.business_id == business_id,
        UserBusinessRole.status == "active",
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _get_business_by_uuid(
    db: AsyncSession, business_uuid: str, for_update: bool = False
) -> Business:
    """按 UUID 查询商业实体（软删除过滤）"""
    try:
        uid = UUID(business_uuid)
    except (ValueError, AttributeError):
        raise ValidationException("商业实体 ID 格式错误")

    stmt = select(Business).where(
        Business.uuid == uid, Business.deleted_at.is_(None)
    )
    if for_update:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    biz = result.scalar_one_or_none()
    if biz is None:
        raise NotFoundException("商业实体不存在")
    return biz


def _business_dict(biz: Business, role: Optional[str] = None) -> dict:
    """构建商业实体响应数据（对外用 uuid 作为 id）"""
    data = {
        "id": str(biz.uuid),
        "name": biz.name,
        "slug": biz.slug,
        "category": biz.category,
        "sub_category": biz.sub_category,
        "business_model": biz.business_model,
        "address": biz.address,
        "city": biz.city,
        "province": biz.province,
        "country": biz.country,
        "timezone": biz.timezone,
        "currency": biz.currency,
        "status": biz.status,
        "owner_id": None,
        "agent_id": None,
        "config": biz.config or {},
        "created_at": biz.created_at.isoformat() if biz.created_at else None,
        "updated_at": biz.updated_at.isoformat() if biz.updated_at else None,
    }
    # owner_id / agent_id 对外也用 uuid（需在查询时关联；此处简化：返回 None，由详情接口补充）
    return data


async def create_business(
    db: AsyncSession, user_id: int, req
) -> Business:
    """创建商业实体 - 创建者自动成为 owner"""
    # slug 唯一性校验
    existing = await db.execute(
        select(Business.id).where(Business.slug == req.slug)
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictException("slug 已被占用")

    # 组装 config
    config = dict(DEFAULT_CONFIG)
    if req.template:
        config["template"] = req.template

    biz = Business(
        name=req.name,
        slug=req.slug,
        category=req.category,
        sub_category=req.sub_category,
        business_model=req.business_model,
        address=req.address,
        city=req.city,
        province=req.province,
        country=req.country or "CN",
        timezone=req.timezone or "Asia/Shanghai",
        currency=req.currency or "CNY",
        status="active",
        owner_id=user_id,
        config=config,
    )
    db.add(biz)
    await db.flush()  # 拿到 biz.id

    # 创建者自动成为 owner
    role = UserBusinessRole(
        user_id=user_id,
        business_id=biz.id,
        role=Role.OWNER.value,
        status="active",
    )
    db.add(role)
    await db.commit()
    await db.refresh(biz)
    return biz


async def list_my_businesses(
    db: AsyncSession,
    user_id: int,
    status: Optional[str],
    page: int,
    page_size: int,
) -> Tuple[list, int]:
    """获取当前用户所属商业实体列表"""
    stmt = (
        select(Business, UserBusinessRole.role)
        .join(UserBusinessRole, UserBusinessRole.business_id == Business.id)
        .where(
            UserBusinessRole.user_id == user_id,
            UserBusinessRole.status == "active",
            Business.deleted_at.is_(None),
        )
        .order_by(Business.created_at.desc())
    )
    if status:
        stmt = stmt.where(Business.status == status)

    # 计算总数
    count_stmt = (
        select(func.count())
        .select_from(Business)
        .join(UserBusinessRole, UserBusinessRole.business_id == Business.id)
        .where(
            UserBusinessRole.user_id == user_id,
            UserBusinessRole.status == "active",
            Business.deleted_at.is_(None),
        )
    )
    if status:
        count_stmt = count_stmt.where(Business.status == status)
    total = (await db.execute(count_stmt)).scalar_one()

    # 分页
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)

    items = []
    for biz, role in result:
        items.append({
            "id": str(biz.uuid),
            "name": biz.name,
            "slug": biz.slug,
            "category": biz.category,
            "sub_category": biz.sub_category,
            "status": biz.status,
            "role": role,
            "currency": biz.currency,
            "timezone": biz.timezone,
            "created_at": biz.created_at.isoformat() if biz.created_at else None,
        })
    return items, total


async def get_business_detail(
    db: AsyncSession, user_id: int, business_uuid: str
) -> Tuple[Business, str, Optional[Agent]]:
    """获取商业实体详情 - 校验成员"""
    biz = await _get_business_by_uuid(db, business_uuid)
    role = await _check_membership(db, user_id, biz.id)
    if role is None:
        raise PermissionException("无权限访问该商业实体")

    # 查询绑定的 Agent
    agent = None
    if biz.agent_id is not None:
        agent_result = await db.execute(select(Agent).where(Agent.id == biz.agent_id))
        agent = agent_result.scalar_one_or_none()

    return biz, role, agent


async def update_business(
    db: AsyncSession, user_id: int, business_uuid: str, req
) -> Business:
    """更新商业实体基础信息 - 需要 owner/manager"""
    biz = await _get_business_by_uuid(db, business_uuid, for_update=True)
    role = await _check_membership(db, user_id, biz.id)
    if role is None:
        raise PermissionException("无权限访问该商业实体")
    if role not in (Role.OWNER.value, Role.MANAGER.value, Role.SUPER_ADMIN.value):
        raise PermissionException("权限不足，需要 owner 或 manager 角色")

    # 按字段更新
    update_fields = [
        "name", "category", "sub_category", "business_model",
        "address", "city", "province", "country", "timezone", "currency",
    ]
    changed = False
    for field in update_fields:
        val = getattr(req, field, None)
        if val is not None:
            setattr(biz, field, val)
            changed = True

    if not changed:
        raise ValidationException("至少需要提供一个更新字段")

    await db.commit()
    await db.refresh(biz)
    return biz


async def update_business_config(
    db: AsyncSession, user_id: int, business_uuid: str, req
) -> dict:
    """更新商业实体经营参数 - 需要 owner/manager"""
    biz = await _get_business_by_uuid(db, business_uuid, for_update=True)
    role = await _check_membership(db, user_id, biz.id)
    if role is None:
        raise PermissionException("无权限访问该商业实体")
    if role not in (Role.OWNER.value, Role.MANAGER.value, Role.SUPER_ADMIN.value):
        raise PermissionException("权限不足，需要 owner 或 manager 角色")

    config = dict(biz.config or {})

    config_fields = [
        "business_hours", "min_profit_rate", "inventory_alert_threshold",
        "price_adjust_approval_threshold", "daily_loss_limit",
        "auto_approve_low_risk", "notify_config",
    ]
    changed = False
    for field in config_fields:
        val = getattr(req, field, None)
        if val is not None:
            config[field] = val
            changed = True

    if not changed:
        raise ValidationException("至少需要提供一个配置字段")

    biz.config = config
    await db.commit()
    await db.refresh(biz)
    return biz.config


async def get_business_stats(
    db: AsyncSession, user_id: int, business_uuid: str, period: str
) -> dict:
    """获取商业实体经营统计概览"""
    biz = await _get_business_by_uuid(db, business_uuid)
    role = await _check_membership(db, user_id, biz.id)
    if role is None:
        raise PermissionException("无权限访问该商业实体")

    # 计算时间范围
    now = datetime.now(timezone.utc)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7d":
        start = now - timedelta(days=7)
    elif period == "30d":
        start = now - timedelta(days=30)
    else:
        raise ValidationException("period 必须是 today / 7d / 30d 之一")

    biz_id = biz.id

    # 销售额 + 订单数（已支付订单）
    sales_stmt = select(
        func.coalesce(func.sum(Order.total_amount), 0),
        func.count(),
    ).where(
        Order.business_id == biz_id,
        Order.paid_at.is_not(None),
        Order.deleted_at.is_(None),
        Order.created_at >= start,
    )
    sales_result = await db.execute(sales_stmt)
    sales_amount, sales_count = sales_result.one()

    # 库存预警数（stock_qty <= min_stock 且 min_stock > 0）
    alert_stmt = select(func.count()).select_from(SKU).where(
        SKU.business_id == biz_id,
        SKU.deleted_at.is_(None),
        SKU.min_stock > 0,
        SKU.stock_qty <= SKU.min_stock,
    )
    inventory_alerts = (await db.execute(alert_stmt)).scalar_one()

    # 待处理工单数
    wo_stmt = select(func.count()).select_from(WorkOrder).where(
        WorkOrder.business_id == biz_id,
        WorkOrder.status.in_(["pending", "approved", "executing"]),
    )
    pending_work_orders = (await db.execute(wo_stmt)).scalar_one()

    # 活跃告警数
    alert_count_stmt = select(func.count()).select_from(Alert).where(
        Alert.business_id == biz_id,
        Alert.status == "active",
    )
    active_alerts = (await db.execute(alert_count_stmt)).scalar_one()

    # Agent 状态
    agent_stmt = select(Agent.status).where(Agent.business_id == biz_id).limit(1)
    agent_status = (await db.execute(agent_stmt)).scalar_one_or_none()
    if agent_status is None:
        agent_status = "pending"

    # 商品数 + SKU 数
    product_count = (await db.execute(
        select(func.count()).select_from(Product).where(
            Product.business_id == biz_id, Product.deleted_at.is_(None)
        )
    )).scalar_one()
    sku_count = (await db.execute(
        select(func.count()).select_from(SKU).where(
            SKU.business_id == biz_id, SKU.deleted_at.is_(None)
        )
    )).scalar_one()

    # 客单价
    avg_order = float(sales_amount) / sales_count if sales_count > 0 else 0.0

    return {
        "period": period,
        "sales_amount": float(sales_amount),
        "sales_count": sales_count,
        "avg_order_value": round(avg_order, 2),
        "inventory_alerts": inventory_alerts,
        "pending_work_orders": pending_work_orders,
        "active_alerts": active_alerts,
        "agent_status": agent_status,
        "product_count": product_count,
        "sku_count": sku_count,
    }
