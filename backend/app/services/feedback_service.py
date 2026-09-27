"""人类反馈学习服务 - 审批反馈、策略建议、自主级别管理

M4-2 范围：
1. 审批拒绝/批准 → 写入 feedback 记忆 + 统计
2. 基于历史反馈生成策略调整建议
3. 策略版本管理（用 Agent.config.strategy_version 存版本号）
4. Agent 自主级别（L0-L4）管理
5. 审批通过率趋势统计

设计要点：
- 反馈记忆复用 AgentMemory（memory_type=feedback）
- 策略版本存在 Agent.config 中：{"strategy_version": N, "strategy": {...}}
- 自主级别直接改 Agent.autonomy_level 字段
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.types import utcnow_naive
from app.models.work_order import WorkOrder, ApprovalAction
from app.models.agent import Agent, AgentMemory
from app.services.memory_service import create_memory

logger = logging.getLogger(__name__)


# ===== 反馈写入 =====

async def record_approval_feedback(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    work_order: WorkOrder,
    action: str,  # "approve" / "reject"
    comment: Optional[str] = None,
    approver_id: int = 0,
) -> Optional[AgentMemory]:
    """审批动作 → 写入反馈记忆

    - reject：写入高重要度 feedback 记忆，供后续决策参考
    - approve：也记录（重要度较低），用于统计通过率
    """
    if action == "reject":
        title = f"审批被拒：{work_order.title[:40]}"
        content = (
            f"工单 #{work_order.id}（{work_order.order_type}）被审批人 {approver_id} 拒绝。\n"
            f"拒绝原因：{comment or '无'}\n"
            f"工单参数：{work_order.params}\n"
            f"原始原因：{work_order.reason or '无'}"
        )
        importance = 5  # 拒绝反馈高重要度
        tags = ["反馈", "拒绝", work_order.order_type]
    else:  # approve
        title = f"审批通过：{work_order.title[:40]}"
        content = (
            f"工单 #{work_order.id}（{work_order.order_type}）被审批人 {approver_id} 批准。\n"
            f"审批意见：{comment or '无'}\n"
            f"工单参数：{work_order.params}"
        )
        importance = 2  # 批准反馈低重要度
        tags = ["反馈", "批准", work_order.order_type]

    try:
        memory = await create_memory(
            db, business_id, agent_id,
            memory_type="feedback",
            title=title,
            content=content,
            tags=tags,
            importance=importance,
            source="feedback",
            source_id=work_order.id,
            metadata_={
                "work_order_id": work_order.id,
                "order_type": work_order.order_type,
                "action": action,
                "approver_id": approver_id,
            },
        )
        logger.info(
            f"[FeedbackService] 写入反馈记忆 {memory.id}（{action}, wo={work_order.id}）"
        )
        return memory
    except Exception as e:
        logger.warning(f"[FeedbackService] 写入反馈记忆失败：{e}")
        return None


# ===== 反馈统计 =====

async def get_feedback_stats(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    days: int = 30,
) -> dict:
    """审批反馈统计：通过率趋势 + 按类型统计

    Returns:
        {
            "total": N,
            "approved": N,
            "rejected": N,
            "approval_rate": 0.85,
            "by_order_type": {"adjust_price": {"approved": 3, "rejected": 1, "rate": 0.75}, ...},
            "trend": [{"date": "...", "approved": N, "rejected": N, "rate": 0.x}, ...],
        }
    """
    now = utcnow_naive()
    start = now - timedelta(days=days)

    # 从 feedback 记忆中统计
    stmt = select(AgentMemory).where(
        AgentMemory.business_id == business_id,
        AgentMemory.agent_id == agent_id,
        AgentMemory.memory_type == "feedback",
        AgentMemory.created_at >= start,
    )
    memories = (await db.execute(stmt)).scalars().all()

    approved = 0
    rejected = 0
    by_type = {}
    daily = {}

    for m in memories:
        meta = m.metadata_ or {}
        action = meta.get("action", "")
        order_type = meta.get("order_type", "unknown")
        date_str = m.created_at.strftime("%Y-%m-%d") if m.created_at else "unknown"

        # action 映射：approve → approved, reject → rejected
        action_key = "approved" if action == "approve" else "rejected" if action == "reject" else None
        if action_key is None:
            continue

        if action == "approve":
            approved += 1
        elif action == "reject":
            rejected += 1

        if order_type not in by_type:
            by_type[order_type] = {"approved": 0, "rejected": 0}
        by_type[order_type][action_key] += 1

        if date_str not in daily:
            daily[date_str] = {"approved": 0, "rejected": 0}
        daily[date_str][action_key] += 1

    total = approved + rejected
    approval_rate = round(approved / total, 4) if total > 0 else 0.0

    # 计算各类型通过率
    for ot, counts in by_type.items():
        ot_total = counts["approved"] + counts["rejected"]
        counts["rate"] = round(counts["approved"] / ot_total, 4) if ot_total > 0 else 0.0
        counts["total"] = ot_total

    # 趋势（按日期排序）
    trend = [
        {
            "date": d,
            "approved": v["approved"],
            "rejected": v["rejected"],
            "rate": round(v["approved"] / (v["approved"] + v["rejected"]), 4)
            if (v["approved"] + v["rejected"]) > 0 else 0.0,
        }
        for d, v in sorted(daily.items())
    ]

    return {
        "days": days,
        "total": total,
        "approved": approved,
        "rejected": rejected,
        "approval_rate": approval_rate,
        "by_order_type": by_type,
        "trend": trend[-14:],  # 最近 14 天
    }


# ===== 策略建议生成 =====

async def generate_strategy_suggestion(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
) -> dict:
    """基于历史反馈生成策略调整建议

    逻辑：
    - 某类工单被拒率 > 50%：建议降低该类操作的自主级别（更保守）
    - 某类工单通过率 100% 且数量 > 5：建议提升该类操作的自主级别
    - 总体通过率 < 60%：建议降低整体自主级别
    - 总体通过率 > 90% 且工单数 > 10：建议提升整体自主级别
    """
    stats = await get_feedback_stats(db, business_id, agent_id, days=30)
    suggestions = []

    by_type = stats.get("by_order_type", {})
    overall_rate = stats.get("approval_rate", 0)
    overall_total = stats.get("total", 0)

    # 按类型分析
    for order_type, type_stats in by_type.items():
        rate = type_stats.get("rate", 0)
        total = type_stats.get("total", 0)
        if total < 3:
            continue  # 样本太少不分析

        if rate < 0.5:
            suggestions.append({
                "type": "downgrade_type",
                "target": order_type,
                "severity": "high",
                "message": (
                    f"工单类型 '{order_type}' 被拒率 {round((1-rate)*100, 1)}%，"
                    f"建议降低该类操作的自主级别或调整参数规则。"
                ),
                "current_rate": rate,
            })
        elif rate >= 0.95 and total >= 5:
            suggestions.append({
                "type": "upgrade_type",
                "target": order_type,
                "severity": "low",
                "message": (
                    f"工单类型 '{order_type}' 通过率 {round(rate*100, 1)}%，"
                    f"可考虑提升该类操作的自主级别。"
                ),
                "current_rate": rate,
            })

    # 总体分析
    if overall_total >= 5:
        if overall_rate < 0.6:
            suggestions.append({
                "type": "downgrade_overall",
                "target": "all",
                "severity": "high",
                "message": (
                    f"总体审批通过率 {round(overall_rate*100, 1)}%，"
                    f"建议降低 Agent 整体自主级别。"
                ),
                "current_rate": overall_rate,
            })
        elif overall_rate >= 0.9 and overall_total >= 10:
            suggestions.append({
                "type": "upgrade_overall",
                "target": "all",
                "severity": "low",
                "message": (
                    f"总体审批通过率 {round(overall_rate*100, 1)}%，"
                    f"可考虑提升 Agent 整体自主级别。"
                ),
                "current_rate": overall_rate,
            })

    # 按严重度排序
    severity_order = {"high": 0, "medium": 1, "low": 2}
    suggestions.sort(key=lambda s: severity_order.get(s["severity"], 9))

    return {
        "stats": stats,
        "suggestions": suggestions,
        "suggestion_count": len(suggestions),
    }


# ===== 策略版本管理 =====

async def get_strategy(
    db: AsyncSession, business_id: int, agent_id: int
) -> Optional[dict]:
    """获取当前策略"""
    stmt = select(Agent).where(
        Agent.id == agent_id,
        Agent.business_id == business_id,
    )
    agent = (await db.execute(stmt)).scalar_one_or_none()
    if agent is None:
        return None
    config = agent.config or {}
    return {
        "agent_id": agent_id,
        "strategy_version": config.get("strategy_version", 0),
        "strategy": config.get("strategy", {}),
        "strategy_history": config.get("strategy_history", []),
        "autonomy_level": agent.autonomy_level,
    }


async def update_strategy(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    strategy: dict,
    note: str = "",
) -> Tuple[Optional[dict], Optional[str]]:
    """更新策略（版本号 +1，旧版本存入 history）"""
    stmt = select(Agent).where(
        Agent.id == agent_id,
        Agent.business_id == business_id,
    )
    agent = (await db.execute(stmt)).scalar_one_or_none()
    if agent is None:
        return None, "Agent 不存在或无权访问"

    config = dict(agent.config or {})
    old_version = config.get("strategy_version", 0)
    old_strategy = config.get("strategy", {})

    # 旧策略存入 history
    history = config.get("strategy_history", [])
    if old_strategy:
        history.append({
            "version": old_version,
            "strategy": old_strategy,
            "note": note,
            "updated_at": utcnow_naive().isoformat(),
        })
        # 最多保留 20 个历史版本
        history = history[-20:]

    config["strategy_version"] = old_version + 1
    config["strategy"] = strategy
    config["strategy_history"] = history
    agent.config = config
    await db.commit()
    await db.refresh(agent)

    logger.info(
        f"[FeedbackService] Agent {agent_id} 策略更新 v{old_version} → v{old_version + 1}"
    )
    return {
        "agent_id": agent_id,
        "strategy_version": old_version + 1,
        "strategy": strategy,
        "strategy_history": history,
    }, None


async def rollback_strategy(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    target_version: int,
) -> Tuple[Optional[dict], Optional[str]]:
    """回滚到指定策略版本"""
    stmt = select(Agent).where(
        Agent.id == agent_id,
        Agent.business_id == business_id,
    )
    agent = (await db.execute(stmt)).scalar_one_or_none()
    if agent is None:
        return None, "Agent 不存在或无权访问"

    config = dict(agent.config or {})
    history = config.get("strategy_history", [])

    # 在 history 中找目标版本
    target = None
    for h in history:
        if h.get("version") == target_version:
            target = h
            break

    if target is None:
        return None, f"策略版本 {target_version} 不存在于历史记录"

    old_version = config.get("strategy_version", 0)
    # 把当前策略追加到 history
    current = config.get("strategy", {})
    history.append({
        "version": old_version,
        "strategy": current,
        "note": "回滚前自动保存",
        "updated_at": utcnow_naive().isoformat(),
    })
    history = history[-20:]

    config["strategy_version"] = old_version + 1
    config["strategy"] = target["strategy"]
    config["strategy_history"] = history
    agent.config = config
    await db.commit()
    await db.refresh(agent)

    logger.info(f"[FeedbackService] Agent {agent_id} 策略回滚到 v{target_version}")
    return {
        "agent_id": agent_id,
        "strategy_version": old_version + 1,
        "strategy": target["strategy"],
        "rolled_back_to": target_version,
        "strategy_history": history,
    }, None


# ===== 自主级别管理 =====

async def set_autonomy_level(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    autonomy_level: str,
) -> Tuple[Optional[Agent], Optional[str]]:
    """设置 Agent 自主级别 L0-L4

    L0：全人工，所有操作需审批
    L1：建议级别，只生成建议
    L2：低风险自动执行
    L3：中风险自动执行
    L4：全自动（高风险也自动执行）
    """
    valid_levels = {"L0", "L1", "L2", "L3", "L4"}
    if autonomy_level not in valid_levels:
        return None, f"非法自主级别：{autonomy_level}（应为 {valid_levels}）"

    stmt = select(Agent).where(
        Agent.id == agent_id,
        Agent.business_id == business_id,
    )
    agent = (await db.execute(stmt)).scalar_one_or_none()
    if agent is None:
        return None, "Agent 不存在或无权访问"

    old_level = agent.autonomy_level
    agent.autonomy_level = autonomy_level
    await db.commit()
    await db.refresh(agent)

    logger.info(
        f"[FeedbackService] Agent {agent_id} 自主级别 {old_level} → {autonomy_level}"
    )
    return agent, None


# 自主级别 → 自动审批范围说明
AUTONOMY_LEVEL_DESC = {
    "L0": "全人工：所有操作需人工审批，Agent 只提供建议",
    "L1": "建议级别：Agent 只生成建议，不自动执行任何操作",
    "L2": "低风险自动：低风险操作（如采购建议）自动执行，中高风险需审批",
    "L3": "中风险自动：低风险和中风险操作自动执行，高风险需审批",
    "L4": "全自动：所有操作自动执行，无需人工审批",
}
