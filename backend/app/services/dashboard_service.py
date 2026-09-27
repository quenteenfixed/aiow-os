"""仪表盘数据聚合服务

M4-3 管理仪表盘：
1. 经营总览：销售额、订单数、客单价、新增客户
2. 销售趋势：按日/周/月聚合
3. 库存趋势：出入库流水
4. Agent 活动：工单数量、状态分布、自主级别分布
5. 告警汇总：活跃告警数、按类型/级别分布
6. 效率对比：Agent 处理 vs 人工处理
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func, and_, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.types import utcnow_naive
from app.models.order import Order, OrderItem
from app.models.inventory import InventoryLog
from app.models.work_order import WorkOrder
from app.models.operations import Alert
from app.models.agent import Agent

logger = logging.getLogger(__name__)


def _date_truncate(dt: datetime, granularity: str = "day") -> str:
    """截断日期到指定粒度用于分组"""
    if granularity == "day":
        return dt.strftime("%Y-%m-%d")
    elif granularity == "week":
        # ISO 周
        iso = dt.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    elif granularity == "month":
        return dt.strftime("%Y-%m")
    return dt.strftime("%Y-%m-%d")


# ===== 经营总览 =====

async def get_overview(
    db: AsyncSession,
    business_id: int,
    days: int = 7,
) -> dict:
    """经营总览指标

    Returns:
        {
            "period": {"days": 7, "from": "...", "to": "..."},
            "sales": {
                "total_amount": 12345.00,  # 销售额（已支付订单）
                "order_count": 50,
                "avg_order_value": 246.90,  # 客单价
            },
            "inventory": {
                "total_in": 100,   # 入库总量
                "total_out": 80,   # 出库总量
                "net_change": 20,
            },
            "work_orders": {
                "total": 30,
                "by_status": {"pending": 5, "approved": 20, "rejected": 3, "executed": 2},
            },
            "alerts": {
                "active": 2,
                "by_level": {"critical": 1, "warning": 1, "info": 0},
            },
            "agents": {
                "total": 3,
                "by_autonomy_level": {"L2": 2, "L3": 1},
            },
        }
    """
    now = utcnow_naive()
    start = now - timedelta(days=days)

    # 1. 销售数据（已支付订单）
    sales_stmt = select(
        func.coalesce(func.sum(Order.payable_amount), Decimal("0")),
        func.count(Order.id),
    ).where(
        Order.business_id == business_id,
        Order.deleted_at.is_(None),
        Order.payment_status == "paid",
        Order.paid_at >= start,
        Order.paid_at <= now,
    )
    total_amount, order_count = (await db.execute(sales_stmt)).first() or (Decimal("0"), 0)

    avg_order_value = float(total_amount) / order_count if order_count > 0 else 0.0

    # 2. 库存流水
    inv_stmt = select(
        func.coalesce(func.sum(
            InventoryLog.change_qty
        ).filter(InventoryLog.change_type.in_(["in", "purchase"])), 0),
        func.coalesce(func.sum(
            InventoryLog.change_qty
        ).filter(InventoryLog.change_type.in_(["out", "sale", "adjust_out"])), 0),
    ).where(
        InventoryLog.business_id == business_id,
        InventoryLog.created_at >= start,
        InventoryLog.created_at <= now,
    )
    inv_in, inv_out = (await db.execute(inv_stmt)).first() or (0, 0)

    # 3. 工单统计
    wo_stmt = select(WorkOrder).where(
        WorkOrder.business_id == business_id,
        WorkOrder.created_at >= start,
        WorkOrder.created_at <= now,
    )
    work_orders = (await db.execute(wo_stmt)).scalars().all()
    wo_by_status = {}
    for wo in work_orders:
        wo_by_status[wo.status] = wo_by_status.get(wo.status, 0) + 1

    # 4. 活跃告警
    alert_stmt = select(Alert).where(
        Alert.business_id == business_id,
        Alert.status == "active",
    )
    alerts = (await db.execute(alert_stmt)).scalars().all()
    alert_by_severity = {}
    for a in alerts:
        alert_by_severity[a.level] = alert_by_severity.get(a.level, 0) + 1

    # 5. Agent 统计
    agent_stmt = select(Agent).where(Agent.business_id == business_id)
    agents = (await db.execute(agent_stmt)).scalars().all()
    agent_by_level = {}
    for a in agents:
        level = a.autonomy_level or "L0"
        agent_by_level[level] = agent_by_level.get(level, 0) + 1

    return {
        "period": {
            "days": days,
            "from": start.isoformat(),
            "to": now.isoformat(),
        },
        "sales": {
            "total_amount": float(total_amount),
            "order_count": int(order_count),
            "avg_order_value": round(avg_order_value, 2),
        },
        "inventory": {
            "total_in": int(inv_in),
            "total_out": int(inv_out),
            "net_change": int(inv_in) + int(inv_out),  # out 为负数
        },
        "work_orders": {
            "total": len(work_orders),
            "by_status": wo_by_status,
        },
        "alerts": {
            "active": len(alerts),
            "by_level": alert_by_severity,
        },
        "agents": {
            "total": len(agents),
            "by_autonomy_level": agent_by_level,
        },
    }


# ===== 销售趋势 =====

async def get_sales_trend(
    db: AsyncSession,
    business_id: int,
    days: int = 30,
    granularity: str = "day",  # day/week/month
) -> list:
    """销售趋势（按日/周/月）

    Returns:
        [{"date": "2026-09-26", "amount": 1000.0, "order_count": 10, "avg_value": 100.0}, ...]
    """
    now = utcnow_naive()
    start = now - timedelta(days=days)

    stmt = select(Order).where(
        Order.business_id == business_id,
        Order.deleted_at.is_(None),
        Order.payment_status == "paid",
        Order.paid_at >= start,
        Order.paid_at <= now,
    ).order_by(Order.paid_at)
    orders = (await db.execute(stmt)).scalars().all()

    # 聚合
    buckets = {}
    for o in orders:
        key = _date_truncate(o.paid_at, granularity)
        if key not in buckets:
            buckets[key] = {"amount": Decimal("0"), "order_count": 0}
        buckets[key]["amount"] += o.payable_amount
        buckets[key]["order_count"] += 1

    trend = []
    for key in sorted(buckets.keys()):
        b = buckets[key]
        count = b["order_count"]
        trend.append({
            "date": key,
            "amount": float(b["amount"]),
            "order_count": count,
            "avg_value": round(float(b["amount"]) / count, 2) if count > 0 else 0.0,
        })
    return trend


# ===== 库存趋势 =====

async def get_inventory_trend(
    db: AsyncSession,
    business_id: int,
    days: int = 30,
) -> list:
    """库存出入库趋势（按日）

    Returns:
        [{"date": "...", "in": 100, "out": -50, "net": 50}, ...]
    """
    now = utcnow_naive()
    start = now - timedelta(days=days)

    stmt = select(InventoryLog).where(
        InventoryLog.business_id == business_id,
        InventoryLog.created_at >= start,
        InventoryLog.created_at <= now,
    ).order_by(InventoryLog.created_at)
    logs = (await db.execute(stmt)).scalars().all()

    buckets = {}
    for log in logs:
        key = _date_truncate(log.created_at, "day")
        if key not in buckets:
            buckets[key] = {"in": 0, "out": 0}
        if log.change_qty > 0:
            buckets[key]["in"] += log.change_qty
        else:
            buckets[key]["out"] += log.change_qty  # 负数

    trend = []
    for key in sorted(buckets.keys()):
        b = buckets[key]
        trend.append({
            "date": key,
            "in": b["in"],
            "out": b["out"],
            "net": b["in"] + b["out"],
        })
    return trend


# ===== Agent 活动 =====

async def get_agent_activity(
    db: AsyncSession,
    business_id: int,
    days: int = 7,
) -> dict:
    """Agent 活动统计

    Returns:
        {
            "total_work_orders": N,
            "by_agent": {agent_id: {"name": ..., "count": N, "by_status": {...}}},
            "by_type": {"adjust_price": 5, "suggest_purchase": 3, ...},
        }
    """
    now = utcnow_naive()
    start = now - timedelta(days=days)

    stmt = select(WorkOrder).where(
        WorkOrder.business_id == business_id,
        WorkOrder.created_at >= start,
        WorkOrder.created_at <= now,
    )
    work_orders = (await db.execute(stmt)).scalars().all()

    by_agent = {}
    by_type = {}
    for wo in work_orders:
        aid = wo.agent_id or 0
        if aid not in by_agent:
            by_agent[aid] = {"count": 0, "by_status": {}}
        by_agent[aid]["count"] += 1
        by_agent[aid]["by_status"][wo.status] = by_agent[aid]["by_status"].get(wo.status, 0) + 1

        by_type[wo.order_type] = by_type.get(wo.order_type, 0) + 1

    # 补充 Agent 名称
    agent_ids = list(by_agent.keys())
    if agent_ids:
        agent_stmt = select(Agent.id, Agent.name).where(
            Agent.business_id == business_id,
            Agent.id.in_(agent_ids),
        )
        agent_names = dict((await db.execute(agent_stmt)).all())
        for aid in by_agent:
            by_agent[aid]["name"] = agent_names.get(aid, f"Agent #{aid}")

    return {
        "total_work_orders": len(work_orders),
        "by_agent": by_agent,
        "by_type": by_type,
    }


# ===== 效率对比：Agent vs 人工 =====

async def get_efficiency_comparison(
    db: AsyncSession,
    business_id: int,
    days: int = 30,
) -> dict:
    """Agent 自主运营 vs 人工处理效率对比

    对比维度：
    - 工单数量
    - 审批通过率
    - 平均处理时长
    - 拒绝率

    说明：agent_id != null 视为 Agent 创建，否则人工创建
    """
    now = utcnow_naive()
    start = now - timedelta(days=days)

    stmt = select(WorkOrder).where(
        WorkOrder.business_id == business_id,
        WorkOrder.created_at >= start,
        WorkOrder.created_at <= now,
    )
    work_orders = (await db.execute(stmt)).scalars().all()

    agent_wo = [wo for wo in work_orders if wo.agent_id]
    manual_wo = [wo for wo in work_orders if not wo.agent_id]

    def _calc(group):
        total = len(group)
        if total == 0:
            return {"total": 0, "approved": 0, "rejected": 0, "approval_rate": 0.0,
                    "rejection_rate": 0.0, "avg_processing_minutes": 0.0}
        approved = sum(1 for wo in group if wo.status == "approved")
        rejected = sum(1 for wo in group if wo.status == "rejected")

        # 平均处理时长（从创建到结束）
        durations = []
        for wo in group:
            end = wo.updated_at or wo.created_at
            if wo.created_at and end:
                delta = (end - wo.created_at).total_seconds() / 60
                durations.append(delta)
        avg_minutes = sum(durations) / len(durations) if durations else 0.0

        return {
            "total": total,
            "approved": approved,
            "rejected": rejected,
            "approval_rate": round(approved / total, 4),
            "rejection_rate": round(rejected / total, 4),
            "avg_processing_minutes": round(avg_minutes, 2),
        }

    return {
        "period": {"days": days},
        "agent_created": _calc(agent_wo),
        "manual_created": _calc(manual_wo),
    }


# ===== 告警汇总 =====

async def get_alerts_summary(
    db: AsyncSession,
    business_id: int,
) -> dict:
    """告警汇总"""
    stmt = select(Alert).where(Alert.business_id == business_id)
    alerts = (await db.execute(stmt)).scalars().all()

    active = [a for a in alerts if a.status == "active"]
    resolved = [a for a in alerts if a.status == "resolved"]

    by_type = {}
    by_severity = {}
    for a in active:
        by_type[a.alert_type] = by_type.get(a.alert_type, 0) + 1
        by_severity[a.level] = by_severity.get(a.level, 0) + 1

    return {
        "total": len(alerts),
        "active": len(active),
        "resolved": len(resolved),
        "active_by_type": by_type,
        "active_by_level": by_severity,
    }


# ===== 完整仪表盘数据 =====

async def get_full_dashboard(
    db: AsyncSession,
    business_id: int,
    days: int = 7,
) -> dict:
    """一次性返回完整仪表盘数据"""
    overview = await get_overview(db, business_id, days)
    sales_trend = await get_sales_trend(db, business_id, days=max(days, 30))
    inventory_trend = await get_inventory_trend(db, business_id, days=max(days, 30))
    agent_activity = await get_agent_activity(db, business_id, days)
    efficiency = await get_efficiency_comparison(db, business_id, days=max(days, 30))
    alerts = await get_alerts_summary(db, business_id)

    return {
        "overview": overview,
        "sales_trend": sales_trend,
        "inventory_trend": inventory_trend,
        "agent_activity": agent_activity,
        "efficiency_comparison": efficiency,
        "alerts_summary": alerts,
    }
