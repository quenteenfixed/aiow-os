"""内置查询工具 - 复用 Phase 1 的 service 层

M2-2 范围：10 个基础查询工具
1. search_products - 搜索商品（含 SKU 聚合）
2. get_inventory - 库存列表（轻量，按关键词/状态筛选）
3. list_orders - 订单列表
4. get_order_detail - 订单详情（含明细）
5. get_product - 商品详情（含 SKU 列表）
6. inventory_history - 库存流水（按时间/SKU/类型筛选）
7. check_expiring - 临期商品（基于批次 expire_date）
8. get_customer - 客户详情（含最近 50 单历史）
9. sales_stats - 销售统计（按周期汇总订单）
10. business_overview - 经营概览（商品/库存/订单/客户核心指标聚合）

所有工具 category="read"，gates={"fencing": True, "rate_limit": True}。
服务端身份注入：business_id 由 ToolExecutor 从 SessionContext 注入，不信任 LLM 传入。
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ToolRegistry
from app.models import Customer, Order, OrderItem, Product, SKU
from app.services.product_service import list_products, get_product_detail, _product_dict
from app.services.inventory_service import (
    list_inventory,
    list_inventory_logs,
    list_expiring,
    list_inventory_alerts,
)
from app.services.order_service import list_orders, get_order_detail, get_order_stats
from app.services.customer_service import get_customer_detail, _customer_dict

logger = logging.getLogger(__name__)


# ===== 工具实现函数 =====

async def _search_products(
    db: AsyncSession,
    business_id: int,
    keyword: Optional[str] = None,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
) -> dict:
    """搜索商品 - 复用 product_service.list_products"""
    items, total = await list_products(
        db, business_id,
        keyword=keyword, category=category, brand=brand, status=status,
        tag=None, min_price=None, max_price=None,
        sort_by="created_at", sort_order="desc",
        page=page, page_size=min(page_size, 20),
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def _get_inventory(
    db: AsyncSession,
    business_id: int,
    keyword: Optional[str] = None,
    category: Optional[str] = None,
    sku_code: Optional[str] = None,
    stock_status: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
) -> dict:
    """查询库存 - 复用 inventory_service.list_inventory"""
    items, total = await list_inventory(
        db, business_id,
        keyword=keyword, category=category, sku_code=sku_code,
        stock_status=stock_status,
        sort_by="stock_qty", sort_order="desc",
        page=page, page_size=min(page_size, 20),
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def _list_orders(
    db: AsyncSession,
    business_id: int,
    order_no: Optional[str] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    payment_status: Optional[str] = None,
    customer_keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
) -> dict:
    """查询订单列表 - 复用 order_service.list_orders"""
    items, total = await list_orders(
        db, business_id,
        order_no=order_no, status=status, source=source,
        payment_status=payment_status, customer_keyword=customer_keyword,
        start_date=None, end_date=None,
        min_amount=None, max_amount=None,
        sort_by="created_at", sort_order="desc",
        page=page, page_size=min(page_size, 20),
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def _get_order_detail(
    db: AsyncSession,
    business_id: int,
    order_uuid: str,
) -> dict:
    """查询订单详情"""
    return await get_order_detail(db, business_id, order_uuid)


async def _get_product(
    db: AsyncSession,
    business_id: int,
    product_uuid: str,
) -> dict:
    """商品详情（含 SKU 列表）- 复用 product_service.get_product_detail + _product_dict"""
    product = await get_product_detail(db, business_id, product_uuid)
    return await _product_dict(db, product, include_skus=True)


async def _inventory_history(
    db: AsyncSession,
    business_id: int,
    sku_id: Optional[str] = None,
    change_type: Optional[str] = None,
    operator_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """库存流水 - 复用 inventory_service.list_inventory_logs"""
    items, total = await list_inventory_logs(
        db, business_id,
        sku_id=sku_id, change_type=change_type, operator_type=operator_type,
        start_date=start_date, end_date=end_date,
        page=page, page_size=min(page_size, 50),
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def _check_expiring(
    db: AsyncSession,
    business_id: int,
    days: int = 30,
    category: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """临期商品 - 复用 inventory_service.list_expiring"""
    # 限制 days 范围，避免过大
    days = max(1, min(int(days or 30), 365))
    items, total = await list_expiring(
        db, business_id,
        days=days, category=category,
        page=page, page_size=min(page_size, 50),
    )
    return {
        "items": items, "total": total, "page": page, "page_size": page_size,
        "days_threshold": days,
    }


async def _get_customer(
    db: AsyncSession,
    business_id: int,
    customer_uuid: str,
) -> dict:
    """客户详情（含最近 50 单历史）- 复用 customer_service.get_customer_detail + _customer_dict"""
    customer, orders = await get_customer_detail(db, business_id, customer_uuid)
    return _customer_dict(customer, include_orders=True, orders_data=orders)


async def _sales_stats(
    db: AsyncSession,
    business_id: int,
    period: str = "7d",
) -> dict:
    """销售统计 - 复用 order_service.get_order_stats"""
    # 校验 period 取值
    if period not in ("today", "7d", "30d", "90d"):
        period = "7d"
    return await get_order_stats(db, business_id, period)


async def _business_overview(
    db: AsyncSession,
    business_id: int,
    period: str = "7d",
) -> dict:
    """经营概览 - 聚合商品/库存/订单/客户核心指标

    直接查询，不复用 business_service.get_business_stats（后者需要 user_id + uuid，不适用 Agent 场景）。
    """
    # 校验 period
    if period not in ("today", "7d", "30d"):
        period = "7d"

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7d":
        start = now - timedelta(days=7)
    else:  # 30d
        start = now - timedelta(days=30)

    # === 商品/SKU 总数 ===
    product_count = (await db.execute(
        select(func.count()).select_from(Product).where(
            Product.business_id == business_id,
            Product.deleted_at.is_(None),
        )
    )).scalar_one()
    sku_count = (await db.execute(
        select(func.count()).select_from(SKU).where(
            SKU.business_id == business_id,
            SKU.deleted_at.is_(None),
        )
    )).scalar_one()

    # === 库存指标 ===
    # 库存总值（按 cost_price 估算，无 cost_price 按 price）
    stock_value_stmt = select(
        func.coalesce(func.sum(SKU.stock_qty * func.coalesce(SKU.cost_price, SKU.price)), 0)
    ).where(
        SKU.business_id == business_id,
        SKU.deleted_at.is_(None),
    )
    stock_total_value = float((await db.execute(stock_value_stmt)).scalar_one())

    # 缺货 SKU 数
    out_of_stock_count = (await db.execute(
        select(func.count()).select_from(SKU).where(
            SKU.business_id == business_id,
            SKU.deleted_at.is_(None),
            SKU.stock_qty <= 0,
        )
    )).scalar_one()

    # 低库存 SKU 数（safety_stock > 0 且 stock_qty <= safety_stock）
    low_stock_count = (await db.execute(
        select(func.count()).select_from(SKU).where(
            SKU.business_id == business_id,
            SKU.deleted_at.is_(None),
            SKU.safety_stock > 0,
            SKU.stock_qty <= SKU.safety_stock,
        )
    )).scalar_one()

    # === 订单指标（指定周期内） ===
    sales_stmt = select(
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
    o_total, o_amount, o_completed, o_cancelled, o_refunded = (await db.execute(sales_stmt)).one()
    avg_order = float(o_amount) / o_total if o_total > 0 else 0.0

    # === 客户指标 ===
    customer_count = (await db.execute(
        select(func.count()).select_from(Customer).where(
            Customer.business_id == business_id,
            Customer.deleted_at.is_(None),
        )
    )).scalar_one()

    # 等级分布
    level_stmt = (
        select(Customer.level, func.count(Customer.id))
        .where(
            Customer.business_id == business_id,
            Customer.deleted_at.is_(None),
        )
        .group_by(Customer.level)
    )
    level_rows = (await db.execute(level_stmt)).all()
    level_distribution = {row[0]: row[1] for row in level_rows}
    for lvl in ("normal", "vip", "svip"):
        level_distribution.setdefault(lvl, 0)

    return {
        "period": period,
        "product": {
            "product_count": product_count,
            "sku_count": sku_count,
        },
        "inventory": {
            "stock_total_value": round(stock_total_value, 2),
            "out_of_stock_count": out_of_stock_count,
            "low_stock_count": low_stock_count,
        },
        "orders": {
            "total_orders": o_total,
            "total_amount": round(float(o_amount), 2),
            "avg_order_value": round(avg_order, 2),
            "completed_count": o_completed,
            "cancelled_count": o_cancelled,
            "refunded_count": o_refunded,
        },
        "customers": {
            "total_customers": customer_count,
            "level_distribution": level_distribution,
        },
    }


# ===== 注册函数 =====

def register_builtin_tools(registry: ToolRegistry) -> None:
    """注册 10 个基础查询工具到注册表"""

    # 1. search_products
    registry.register(
        name="search_products",
        description="搜索商品列表，支持按关键词、分类、品牌、状态筛选。返回商品基础信息和 SKU 聚合（sku_count/total_stock/base_price）。常用场景：用户问'xx 商品''xx 库存''有没有 xx'。",
        input_schema={
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "商品名称或 SKU 编码关键词，如'可口可乐'"},
                "category": {"type": "string", "description": "商品分类，如'饮料''零食'"},
                "brand": {"type": "string", "description": "品牌"},
                "status": {"type": "string", "description": "商品状态：draft/listed/published/unlisted/archived"},
                "page": {"type": "integer", "description": "页码，默认 1", "default": 1},
                "page_size": {"type": "integer", "description": "每页数量，默认 10，最大 20", "default": 10},
            },
        },
        handler=_search_products,
        category="read",
        gates={"fencing": True, "rate_limit": True},
    )

    # 2. get_inventory
    registry.register(
        name="get_inventory",
        description="查询库存列表，支持按关键词、分类、SKU 编码、库存状态筛选。返回 SKU 库存数量、安全库存、状态。常用场景：用户问'xx 库存多少''缺货商品''低库存'。",
        input_schema={
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "商品名称或 SKU 编码关键词"},
                "category": {"type": "string", "description": "商品分类"},
                "sku_code": {"type": "string", "description": "精确 SKU 编码"},
                "stock_status": {"type": "string", "description": "库存状态筛选：out_of_stock（缺货）/ low（低库存）"},
                "page": {"type": "integer", "description": "页码，默认 1", "default": 1},
                "page_size": {"type": "integer", "description": "每页数量，默认 10，最大 20", "default": 10},
            },
        },
        handler=_get_inventory,
        category="read",
        gates={"fencing": True, "rate_limit": True},
    )

    # 3. list_orders
    registry.register(
        name="list_orders",
        description="查询订单列表，支持按订单号、状态、来源、付款状态、客户关键词筛选。常用场景：用户问'订单''最近订单''xx 客户订单'。",
        input_schema={
            "type": "object",
            "properties": {
                "order_no": {"type": "string", "description": "精确订单号"},
                "status": {"type": "string", "description": "订单状态：pending/paid/shipped/completed/refunded/cancelled"},
                "source": {"type": "string", "description": "订单来源：pos/online/agent"},
                "payment_status": {"type": "string", "description": "付款状态：unpaid/paid/refunded"},
                "customer_keyword": {"type": "string", "description": "客户姓名或电话关键词"},
                "page": {"type": "integer", "description": "页码，默认 1", "default": 1},
                "page_size": {"type": "integer", "description": "每页数量，默认 10，最大 20", "default": 10},
            },
        },
        handler=_list_orders,
        category="read",
        gates={"fencing": True, "rate_limit": True},
    )

    # 4. get_order_detail
    registry.register(
        name="get_order_detail",
        description="查询单个订单的详细信息，包括订单项明细（商品名/规格/单价/数量/小计）。需要提供订单 UUID（从 list_orders 结果中获取）。",
        input_schema={
            "type": "object",
            "properties": {
                "order_uuid": {"type": "string", "description": "订单 UUID（从 list_orders 结果中获取）"},
            },
            "required": ["order_uuid"],
        },
        handler=_get_order_detail,
        category="read",
        gates={"fencing": True, "rate_limit": True},
    )

    # 5. get_product
    registry.register(
        name="get_product",
        description="查询单个商品的详细信息，包括完整 SKU 列表（sku_code/spec_name/price/stock_qty/safety_stock 等）。需要提供商品 UUID（从 search_products 结果中获取）。",
        input_schema={
            "type": "object",
            "properties": {
                "product_uuid": {"type": "string", "description": "商品 UUID（从 search_products 结果的 id 字段获取）"},
            },
            "required": ["product_uuid"],
        },
        handler=_get_product,
        category="read",
        gates={"fencing": True, "rate_limit": True},
    )

    # 6. inventory_history
    registry.register(
        name="inventory_history",
        description="查询库存流水记录（入库/出库/调整/盘点/退货），支持按 SKU、变动类型、操作来源、时间范围筛选。常用场景：用户问'库存流水''入库记录''出库记录''xx 的库存变化'。",
        input_schema={
            "type": "object",
            "properties": {
                "sku_id": {"type": "string", "description": "SKU UUID（可选，从 get_inventory 结果的 sku_id 获取）"},
                "change_type": {"type": "string", "description": "变动类型：in（入库）/ out（出库）/ adjust（调整）/ check（盘点）/ return（退货）"},
                "operator_type": {"type": "string", "description": "操作来源：user（人工）/ agent（智能体）/ system（系统）"},
                "start_date": {"type": "string", "description": "开始日期 ISO 格式，如 2026-09-01T00:00:00"},
                "end_date": {"type": "string", "description": "结束日期 ISO 格式"},
                "page": {"type": "integer", "description": "页码，默认 1", "default": 1},
                "page_size": {"type": "integer", "description": "每页数量，默认 20，最大 50", "default": 20},
            },
        },
        handler=_inventory_history,
        category="read",
        gates={"fencing": True, "rate_limit": True},
    )

    # 7. check_expiring
    registry.register(
        name="check_expiring",
        description="查询临期商品（基于批次 expire_date，返回 N 天内将到期的批次列表，按到期日期升序）。常用场景：用户问'临期商品''快过期的''到期日''哪些快过期'。",
        input_schema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "查询未来 N 天内将到期的商品，默认 30，最大 365", "default": 30},
                "category": {"type": "string", "description": "商品分类筛选"},
                "page": {"type": "integer", "description": "页码，默认 1", "default": 1},
                "page_size": {"type": "integer", "description": "每页数量，默认 20，最大 50", "default": 20},
            },
        },
        handler=_check_expiring,
        category="read",
        gates={"fencing": True, "rate_limit": True},
    )

    # 8. get_customer
    registry.register(
        name="get_customer",
        description="查询单个客户档案详情，包括等级、累计消费、标签，以及最近 50 笔订单历史。需要提供客户 UUID。常用场景：用户问'xx 客户''xx 会员''客户详情'（先用 list_orders 拿到 customer_id 再查）。",
        input_schema={
            "type": "object",
            "properties": {
                "customer_uuid": {"type": "string", "description": "客户 UUID（从 list_orders 结果中获取，或已知客户 ID）"},
            },
            "required": ["customer_uuid"],
        },
        handler=_get_customer,
        category="read",
        gates={"fencing": True, "rate_limit": True},
    )

    # 9. sales_stats
    registry.register(
        name="sales_stats",
        description="查询销售统计，返回指定周期的订单数、销售额、客单价、完成/取消/退款数。常用场景：用户问'销售统计''今天卖了多少''最近一周营业额''销售额'。",
        input_schema={
            "type": "object",
            "properties": {
                "period": {"type": "string", "description": "统计周期：today（今天）/ 7d（最近7天）/ 30d（最近30天）/ 90d（最近90天），默认 7d", "default": "7d"},
            },
        },
        handler=_sales_stats,
        category="read",
        gates={"fencing": True, "rate_limit": True},
    )

    # 10. business_overview
    registry.register(
        name="business_overview",
        description="经营概览：一次返回商品/SKU 数、库存总值、缺货/低库存数、订单数与销售额、客户数与等级分布等核心指标。常用场景：用户问'经营概览''今天怎么样''生意怎么样''概况''总体情况'。",
        input_schema={
            "type": "object",
            "properties": {
                "period": {"type": "string", "description": "订单统计周期：today / 7d / 30d，默认 7d", "default": "7d"},
            },
        },
        handler=_business_overview,
        category="read",
        gates={"fencing": True, "rate_limit": True},
    )

    logger.info("[builtin] 注册 10 个基础查询工具完成")


# 默认工具白名单（供 agent_service 在 Agent 未配置 allowed_tools 时使用）
DEFAULT_ALLOWED_TOOLS = [
    # 查询类（10 个）
    "search_products",
    "get_inventory",
    "list_orders",
    "get_order_detail",
    "get_product",
    "inventory_history",
    "check_expiring",
    "get_customer",
    "sales_stats",
    "business_overview",
    # 写入类（4 个，M3-2）
    "adjust_price",
    "adjust_stock",
    "process_refund",
    "suggest_purchase",
]
