"""OUPDEL - Observe + Understand 步骤

1. Observe：采集关键经营指标（库存/销售/临期/订单）
2. Understand：基于指标检测异常（库存过低/销量骤降/临期过多/缺货）

设计要点：
- 复用 builtin 工具的查询函数（business_overview/sales_stats/check_expiring/get_inventory）
- 不经过 LLM，直接基于规则检测异常，保证速度
- 灵敏度（sensitivity）调节阈值：high 灵敏度阈值低，更易触发异常
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SKU, Product, Order, InventoryBatch

logger = logging.getLogger(__name__)


# 灵敏度对应的阈值系数（base × factor = 实际阈值）
SENSITIVITY_FACTORS = {
    "low": 0.5,     # 阈值减半，更难触发
    "medium": 1.0,  # 基准
    "high": 1.5,    # 阈值 1.5 倍，更易触发
}


def _factor(sensitivity: str) -> float:
    return SENSITIVITY_FACTORS.get(sensitivity, 1.0)


async def observe(
    db: AsyncSession,
    business_id: int,
    sensitivity: str = "medium",
    config: Optional[dict] = None,
) -> dict:
    """Observe：采集关键经营指标

    Returns:
        {
            "timestamp": "...",
            "sensitivity": "medium",
            "inventory": {...},
            "sales": {...},
            "expiring": {...},
            "products": {...},
        }
    """
    config = config or {}
    factor = _factor(sensitivity)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # 1. 库存指标
    # 缺货 SKU 数 / 低库存 SKU 数 / 库存总值
    stock_value_stmt = select(
        func.coalesce(func.sum(SKU.stock_qty * func.coalesce(SKU.cost_price, SKU.price)), 0)
    ).where(SKU.business_id == business_id, SKU.deleted_at.is_(None))
    stock_total_value = float((await db.execute(stock_value_stmt)).scalar_one())

    out_of_stock_count = (await db.execute(
        select(func.count()).select_from(SKU).where(
            SKU.business_id == business_id,
            SKU.deleted_at.is_(None),
            SKU.stock_qty <= 0,
        )
    )).scalar_one()

    low_stock_count = (await db.execute(
        select(func.count()).select_from(SKU).where(
            SKU.business_id == business_id,
            SKU.deleted_at.is_(None),
            SKU.safety_stock > 0,
            SKU.stock_qty <= SKU.safety_stock,
        )
    )).scalar_one()

    # 低库存商品详情（最多 50 个）
    low_stock_stmt = (
        select(SKU.id, SKU.uuid, SKU.sku_code, SKU.stock_qty, SKU.safety_stock, Product.name)
        .join(Product, SKU.product_id == Product.id)
        .where(
            SKU.business_id == business_id,
            SKU.deleted_at.is_(None),
            SKU.safety_stock > 0,
            SKU.stock_qty <= SKU.safety_stock,
        )
        .order_by(SKU.stock_qty.asc())
        .limit(50)
    )
    low_stock_rows = (await db.execute(low_stock_stmt)).all()
    low_stock_items = [
        {
            "sku_id": str(row.uuid),
            "sku_code": row.sku_code,
            "product_name": row.name,
            "stock_qty": row.stock_qty,
            "safety_stock": row.safety_stock,
            "gap": row.safety_stock - row.stock_qty,
        }
        for row in low_stock_rows
    ]

    # 2. 销售指标（最近 7 天 vs 前 7 天，对比销量）
    seven_days_ago = now - timedelta(days=7)
    fourteen_days_ago = now - timedelta(days=14)

    sales_recent_stmt = select(
        func.count(),
        func.coalesce(func.sum(Order.total_amount), 0),
    ).where(
        Order.business_id == business_id,
        Order.deleted_at.is_(None),
        Order.created_at >= seven_days_ago,
    )
    recent_count, recent_amount = (await db.execute(sales_recent_stmt)).one()

    sales_prev_stmt = select(
        func.count(),
        func.coalesce(func.sum(Order.total_amount), 0),
    ).where(
        Order.business_id == business_id,
        Order.deleted_at.is_(None),
        Order.created_at >= fourteen_days_ago,
        Order.created_at < seven_days_ago,
    )
    prev_count, prev_amount = (await db.execute(sales_prev_stmt)).one()

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_sales_stmt = select(
        func.count(),
        func.coalesce(func.sum(Order.total_amount), 0),
    ).where(
        Order.business_id == business_id,
        Order.deleted_at.is_(None),
        Order.created_at >= today_start,
    )
    today_count, today_amount = (await db.execute(today_sales_stmt)).one()

    # 3. 临期商品
    # 默认 30 天内到期，灵敏度 high 时 60 天
    expiring_days = int(30 * factor)
    expiring_threshold = (now + timedelta(days=expiring_days)).date()
    expiring_stmt = (
        select(InventoryBatch, SKU, Product)
        .join(SKU, InventoryBatch.sku_id == SKU.id)
        .join(Product, SKU.product_id == Product.id)
        .where(
            InventoryBatch.business_id == business_id,
            InventoryBatch.status == "active",
            InventoryBatch.expire_date.is_not(None),
            InventoryBatch.expire_date <= expiring_threshold,
            InventoryBatch.expire_date >= now.date(),
            SKU.deleted_at.is_(None),
        )
        .order_by(InventoryBatch.expire_date.asc())
        .limit(50)
    )
    expiring_rows = (await db.execute(expiring_stmt)).all()
    expiring_items = [
        {
            "batch_id": batch.id,
            "batch_no": batch.batch_no,
            "sku_id": str(sku.uuid),
            "sku_code": sku.sku_code,
            "product_name": product.name,
            "remaining_qty": batch.remaining_qty,
            "expire_date": batch.expire_date.isoformat() if batch.expire_date else None,
            "days_to_expire": (batch.expire_date - now.date()).days if batch.expire_date else None,
        }
        for batch, sku, product in expiring_rows
    ]
    expiring_count = len(expiring_items)

    # 4. 商品总数
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

    return {
        "timestamp": now.isoformat(),
        "sensitivity": sensitivity,
        "inventory": {
            "stock_total_value": round(stock_total_value, 2),
            "out_of_stock_count": out_of_stock_count,
            "low_stock_count": low_stock_count,
            "low_stock_items": low_stock_items,
        },
        "sales": {
            "today_count": today_count,
            "today_amount": round(float(today_amount), 2),
            "recent_7d_count": recent_count,
            "recent_7d_amount": round(float(recent_amount), 2),
            "prev_7d_count": prev_count,
            "prev_7d_amount": round(float(prev_amount), 2),
        },
        "expiring": {
            "days_threshold": expiring_days,
            "count": expiring_count,
            "items": expiring_items,
        },
        "products": {
            "product_count": product_count,
            "sku_count": sku_count,
        },
    }


def understand(observe_data: dict, sensitivity: str = "medium") -> list:
    """Understand：基于采集的指标检测异常

    Returns:
        [
            {
                "type": "low_stock",
                "severity": "P1",
                "title": "10 个 SKU 库存低于安全水位",
                "detail": {...},
                "suggested_action": "suggest_purchase",
                "suggested_params": {...},
            },
            ...
        ]
    """
    anomalies = []
    factor = _factor(sensitivity)
    config_overrides = observe_data.get("_config_overrides", {})

    inv = observe_data.get("inventory", {})
    sales = observe_data.get("sales", {})
    expiring = observe_data.get("expiring", {})

    # === 异常 1：库存过低 ===
    # 灵敏度越高（factor 越大），触发阈值越低，更易报警
    # medium：3 个低库存就报警，high：2 个就报警，low：6 个才报警
    low_stock_threshold = max(1, int(3 / factor))
    low_stock_count = inv.get("low_stock_count", 0)
    out_of_stock_count = inv.get("out_of_stock_count", 0)

    if out_of_stock_count > 0:
        anomalies.append({
            "type": "out_of_stock",
            "severity": "P0",
            "title": f"有 {out_of_stock_count} 个 SKU 已缺货",
            "detail": {"out_of_stock_count": out_of_stock_count},
            "suggested_action": "suggest_purchase",
            "suggested_params": {"reason": f"自主循环：{out_of_stock_count} 个 SKU 缺货，需立即补货"},
        })
    elif low_stock_count >= low_stock_threshold:
        # 找出库存缺口最大的几个 SKU
        low_items = inv.get("low_stock_items", [])[:10]
        anomalies.append({
            "type": "low_stock",
            "severity": "P1",
            "title": f"有 {low_stock_count} 个 SKU 库存低于安全水位",
            "detail": {
                "low_stock_count": low_stock_count,
                "items": low_items,
            },
            "suggested_action": "suggest_purchase",
            "suggested_params": {"reason": f"自主循环：{low_stock_count} 个 SKU 库存偏低，建议补货"},
        })

    # === 异常 2：销量骤降 ===
    # 计算环比变化：recent_7d vs prev_7d，下降超过阈值才报警
    prev_amount = sales.get("prev_7d_amount", 0)
    recent_amount = sales.get("recent_7d_amount", 0)
    drop_threshold = 0.20 / factor  # 灵敏度 high 时阈值低（0.13），low 时高（0.40）

    if prev_amount > 0:
        change_rate = (prev_amount - recent_amount) / prev_amount
        if change_rate > drop_threshold:
            anomalies.append({
                "type": "sales_drop",
                "severity": "P2",
                "title": f"最近 7 天销售额环比下降 {change_rate*100:.1f}%",
                "detail": {
                    "prev_7d_amount": prev_amount,
                    "recent_7d_amount": recent_amount,
                    "change_rate": round(change_rate, 4),
                },
                "suggested_action": "alert_only",
                "suggested_params": {
                    "reason": f"自主循环：销售额环比下降 {change_rate*100:.1f}%，建议关注",
                },
            })

    # === 异常 3：临期过多 ===
    # 临期数阈值：灵敏度越高越易触发，所以用 /factor
    expiring_count = expiring.get("count", 0)
    expiring_threshold = max(1, int(5 / factor))
    if expiring_count >= expiring_threshold:
        anomalies.append({
            "type": "expiring_excess",
            "severity": "P2",
            "title": f"有 {expiring_count} 个批次将在 {expiring.get('days_threshold', 30)} 天内到期",
            "detail": {
                "expiring_count": expiring_count,
                "days_threshold": expiring.get("days_threshold", 30),
                "items": expiring.get("items", [])[:10],
            },
            "suggested_action": "alert_only",
            "suggested_params": {
                "reason": f"自主循环：{expiring_count} 个批次临期，建议促销或调价",
            },
        })

    # 按严重程度排序
    severity_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    anomalies.sort(key=lambda a: severity_order.get(a.get("severity", "P3"), 9))
    return anomalies
