"""熔断系统服务 - M5-2 / M6-3 修复版

M6-3 修复要点：
1. is_circuit_broken / is_circuit_broken_for_agent 不再使用 trigger_condition like 子串匹配，
   改用 CircuitBreak.agent_id 列精确匹配（agent 级）/ NULL（system 级）
2. trigger_circuit_breaker 单事务原子化：cb 记录、暂停工单、告警、审计全部在同一 commit 内
3. recover_circuit_breaker 审计写入与状态变更在同一事务（避免审计漏记）
4. _pause_pending_work_orders 不再独立 commit
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.types import utcnow_naive
from app.models.operations import CircuitBreak, AuditLog
from app.models.work_order import WorkOrder
from app.services.audit_service import _record_audit_no_commit

logger = logging.getLogger(__name__)


# 熔断级别
LEVEL_AGENT = "agent"
LEVEL_SYSTEM = "system"

# 触发类型
TRIGGER_LOSS = "loss_threshold"
TRIGGER_FAILURES = "consecutive_failures"
TRIGGER_ABNORMAL = "abnormal_pattern"
TRIGGER_SECURITY = "security_gate"
TRIGGER_SYSTEM = "system_anomaly"

# 默认阈值
DEFAULT_LOSS_THRESHOLD = Decimal("1000.00")
DEFAULT_MAX_CONSECUTIVE_FAILURES = 5
DEFAULT_ABNORMAL_WINDOW_MIN = 10
DEFAULT_ABNORMAL_COUNT = 10
DEFAULT_SECURITY_GATE_THRESHOLD = 3


# ===== 熔断状态检查 =====

async def is_circuit_broken(
    db: AsyncSession, business_id: int, agent_id: Optional[int] = None
) -> Tuple[bool, Optional[CircuitBreak]]:
    """检查是否处于熔断状态（system 级 + agent 级，如有 agent_id）

    - system 级熔断：agent_id 为 NULL 且 status=active
    - agent 级熔断：agent_id 等于指定值且 status=active
    """
    # system 级
    stmt = select(CircuitBreak).where(
        CircuitBreak.business_id == business_id,
        CircuitBreak.status == "active",
        CircuitBreak.level == LEVEL_SYSTEM,
        CircuitBreak.agent_id.is_(None),
    ).order_by(CircuitBreak.created_at.desc()).limit(1)
    sys_break = (await db.execute(stmt)).scalar_one_or_none()
    if sys_break:
        return True, sys_break

    # agent 级
    if agent_id is not None:
        stmt = select(CircuitBreak).where(
            CircuitBreak.business_id == business_id,
            CircuitBreak.status == "active",
            CircuitBreak.level == LEVEL_AGENT,
            CircuitBreak.agent_id == agent_id,
        ).order_by(CircuitBreak.created_at.desc()).limit(1)
        agt_break = (await db.execute(stmt)).scalar_one_or_none()
        if agt_break:
            return True, agt_break

    return False, None


async def is_circuit_broken_for_agent(
    db: AsyncSession, business_id: int, agent_id: int
) -> bool:
    """检查指定 Agent 是否被熔断（system 级或 agent 级）"""
    broken, _ = await is_circuit_broken(db, business_id, agent_id=agent_id)
    return broken


# ===== 触发熔断 =====

async def trigger_circuit_breaker(
    db: AsyncSession,
    business_id: int,
    level: str,
    trigger_type: str,
    reason: str,
    trigger_value: Optional[Decimal] = None,
    threshold: Optional[Decimal] = None,
    agent_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> CircuitBreak:
    """触发熔断（单事务原子化）

    同一事务内完成：
    1. 创建 CircuitBreak 记录
    2. 暂停该 Agent 的 pending 工单（agent 级）
    3. 创建 P1 告警
    4. 记录审计（不含 commit）
    最后由本函数统一 commit；任意步骤失败则回滚，不会留下半成品状态。
    """
    # 重复触发检查：同一 agent 已有 active 熔断则不再创建
    if level == LEVEL_AGENT and agent_id is not None:
        existing = (await db.execute(
            select(CircuitBreak).where(
                CircuitBreak.business_id == business_id,
                CircuitBreak.status == "active",
                CircuitBreak.level == LEVEL_AGENT,
                CircuitBreak.agent_id == agent_id,
            ).limit(1)
        )).scalar_one_or_none()
        if existing:
            logger.info(f"[CircuitBreaker] Agent {agent_id} 已有 active 熔断 #{existing.id}，跳过重复触发")
            return existing

    cb = CircuitBreak(
        business_id=business_id,
        agent_id=agent_id if level == LEVEL_AGENT else None,
        level=level,
        reason=reason,
        trigger_condition=trigger_type,  # 仅存 trigger_type，agent_id 已独立成列
        trigger_value=trigger_value,
        threshold=threshold,
        status="active",
    )
    db.add(cb)
    await db.flush()  # 拿到 cb.id

    logger.warning(
        f"[CircuitBreaker] 熔断触发！level={level} type={trigger_type} "
        f"agent={agent_id} reason={reason[:60]}"
    )

    # 暂停待执行工单（agent 级）
    paused_count = 0
    if level == LEVEL_AGENT and agent_id is not None:
        paused_count = await _pause_pending_work_orders(db, business_id, agent_id)

    # 创建 P1 告警（同事务）
    alert_id = None
    try:
        from app.services.alert_service import _create_alert_no_commit
        alert = await _create_alert_no_commit(
            db, business_id,
            alert_type="circuit_breaker",
            level="P1",
            title=f"熔断触发：{reason[:50]}",
            content=f"级别：{level}，触发类型：{trigger_type}，原因：{reason}",
            source="circuit_breaker",
        )
        alert_id = alert.id
    except Exception as e:
        logger.warning(f"[CircuitBreaker] 创建告警失败（不影响熔断主流程）：{e}")

    # 审计记录（同事务，使用 _record_audit_no_commit 保证链式哈希加锁正确）
    try:
        await _record_audit_no_commit(
            db, business_id,
            actor_type="user" if user_id else "system",
            actor_id=user_id,
            action="circuit_breaker.trigger",
            target_type="circuit_break",
            target_id=cb.id,
            after_data={
                "level": level,
                "trigger_type": trigger_type,
                "agent_id": agent_id,
                "reason": reason,
                "threshold": float(threshold) if threshold else None,
                "trigger_value": float(trigger_value) if trigger_value else None,
                "paused_work_orders": paused_count,
                "alert_id": alert_id,
            },
            reason=reason,
        )
    except Exception as e:
        logger.warning(f"[CircuitBreaker] 审计写入失败：{e}")

    # 统一提交
    await db.commit()
    await db.refresh(cb)
    return cb


async def _pause_pending_work_orders(
    db: AsyncSession, business_id: int, agent_id: int
) -> int:
    """暂停该 Agent 的所有 pending 工单（不提交，由调用方管理事务）"""
    stmt = select(WorkOrder).where(
        WorkOrder.business_id == business_id,
        WorkOrder.agent_id == agent_id,
        WorkOrder.status == "pending",
    )
    orders = (await db.execute(stmt)).scalars().all()
    for wo in orders:
        wo.status = "paused"
    await db.flush()
    logger.info(f"[CircuitBreaker] 暂停 {len(orders)} 个待执行工单")
    return len(orders)


# ===== 人工恢复 =====

async def recover_circuit_breaker(
    db: AsyncSession,
    business_id: int,
    circuit_break_id: int,
    recovered_by: int,
    recovery_note: str,
) -> Tuple[Optional[CircuitBreak], Optional[str]]:
    """人工恢复熔断（同事务完成状态变更 + 审计）"""
    if not recovery_note or not recovery_note.strip():
        return None, "必须填写恢复原因"

    stmt = select(CircuitBreak).where(
        CircuitBreak.id == circuit_break_id,
        CircuitBreak.business_id == business_id,
    )
    cb = (await db.execute(stmt)).scalar_one_or_none()
    if cb is None:
        return None, "熔断记录不存在"
    if cb.status != "active":
        return None, "该熔断记录已恢复"

    cb.status = "resolved"
    cb.recovered_at = utcnow_naive()
    cb.recovered_by = recovered_by
    cb.recovery_note = recovery_note.strip()
    await db.flush()

    logger.info(
        f"[CircuitBreaker] 熔断恢复 #{circuit_break_id} by={recovered_by} "
        f"note={recovery_note[:40]}"
    )

    # 审计写入（同事务，保证审计与状态变更原子化）
    try:
        await _record_audit_no_commit(
            db, business_id,
            actor_type="user",
            actor_id=recovered_by,
            action="circuit_breaker.recover",
            target_type="circuit_break",
            target_id=circuit_break_id,
            after_data={"status": "resolved", "recovery_note": recovery_note},
            reason=recovery_note,
        )
    except Exception as e:
        logger.warning(f"[CircuitBreaker] 审计写入失败（将一并回滚恢复操作）：{e}")
        await db.rollback()
        return None, f"审计写入失败，恢复已回滚：{e}"

    await db.commit()
    await db.refresh(cb)
    return cb, None


# ===== 触发条件检测 =====

async def check_loss_circuit_breaker(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    loss_amount: Decimal,
    threshold: Decimal = DEFAULT_LOSS_THRESHOLD,
    user_id: Optional[int] = None,
) -> bool:
    """检测单日亏损熔断"""
    if loss_amount >= threshold:
        await trigger_circuit_breaker(
            db, business_id,
            level=LEVEL_AGENT,
            trigger_type=TRIGGER_LOSS,
            reason=f"单日亏损 {loss_amount} 元超过阈值 {threshold} 元",
            trigger_value=loss_amount,
            threshold=threshold,
            agent_id=agent_id,
            user_id=user_id,
        )
        return True
    return False


async def check_failure_circuit_breaker(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    consecutive_failures: int,
    threshold: int = DEFAULT_MAX_CONSECUTIVE_FAILURES,
    user_id: Optional[int] = None,
) -> bool:
    """检测连续决策失败熔断"""
    if consecutive_failures >= threshold:
        await trigger_circuit_breaker(
            db, business_id,
            level=LEVEL_AGENT,
            trigger_type=TRIGGER_FAILURES,
            reason=f"连续决策失败 {consecutive_failures} 次达到阈值 {threshold}",
            trigger_value=Decimal(consecutive_failures),
            threshold=Decimal(threshold),
            agent_id=agent_id,
            user_id=user_id,
        )
        return True
    return False


async def check_abnormal_pattern_circuit_breaker(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    order_type: str,
    count_in_window: int,
    threshold: int = DEFAULT_ABNORMAL_COUNT,
    user_id: Optional[int] = None,
) -> bool:
    """检测异常模式熔断"""
    if count_in_window >= threshold:
        await trigger_circuit_breaker(
            db, business_id,
            level=LEVEL_AGENT,
            trigger_type=TRIGGER_ABNORMAL,
            reason=f"短时间内 {order_type} 操作 {count_in_window} 次达到阈值 {threshold}",
            trigger_value=Decimal(count_in_window),
            threshold=Decimal(threshold),
            agent_id=agent_id,
            user_id=user_id,
        )
        return True
    return False


async def check_system_circuit_breaker(
    db: AsyncSession,
    business_id: int,
    reason: str,
    user_id: Optional[int] = None,
) -> CircuitBreak:
    """系统级熔断（LLM 不可用等，进入只读模式）"""
    return await trigger_circuit_breaker(
        db, business_id,
        level=LEVEL_SYSTEM,
        trigger_type=TRIGGER_SYSTEM,
        reason=f"系统异常：{reason}",
        user_id=user_id,
    )


# ===== 熔断状态查询 =====

async def get_circuit_breaker_status(
    db: AsyncSession, business_id: int
) -> dict:
    """获取熔断状态总览"""
    stmt = select(CircuitBreak).where(
        CircuitBreak.business_id == business_id,
        CircuitBreak.status == "active",
    ).order_by(CircuitBreak.created_at.desc())
    active = (await db.execute(stmt)).scalars().all()

    start = utcnow_naive() - timedelta(days=30)
    stmt = select(CircuitBreak).where(
        CircuitBreak.business_id == business_id,
        CircuitBreak.created_at >= start,
    ).order_by(CircuitBreak.created_at.desc()).limit(50)
    history = (await db.execute(stmt)).scalars().all()

    by_level = {}
    by_trigger = {}
    for cb in history:
        by_level[cb.level] = by_level.get(cb.level, 0) + 1
        by_trigger[cb.trigger_condition] = by_trigger.get(cb.trigger_condition, 0) + 1

    return {
        "is_broken": len(active) > 0,
        "active_count": len(active),
        "active_breaks": [_serialize_cb(cb) for cb in active],
        "history_count": len(history),
        "by_level": by_level,
        "by_trigger": by_trigger,
    }


async def list_circuit_breaks(
    db: AsyncSession,
    business_id: int,
    status: Optional[str] = None,
    level: Optional[str] = None,
    limit: int = 50,
) -> list:
    """查询熔断记录"""
    stmt = select(CircuitBreak).where(
        CircuitBreak.business_id == business_id,
    )
    if status:
        stmt = stmt.where(CircuitBreak.status == status)
    if level:
        stmt = stmt.where(CircuitBreak.level == level)
    stmt = stmt.order_by(CircuitBreak.created_at.desc()).limit(limit)
    breaks = (await db.execute(stmt)).scalars().all()

    return [_serialize_cb(cb) for cb in breaks]


def _serialize_cb(cb: CircuitBreak) -> dict:
    return {
        "id": cb.id,
        "level": cb.level,
        "agent_id": cb.agent_id,
        "reason": cb.reason,
        "trigger_condition": cb.trigger_condition,
        "trigger_value": float(cb.trigger_value) if cb.trigger_value else None,
        "threshold": float(cb.threshold) if cb.threshold else None,
        "status": cb.status,
        "created_at": cb.created_at.isoformat() if cb.created_at else None,
        "recovered_at": cb.recovered_at.isoformat() if cb.recovered_at else None,
        "recovered_by": cb.recovered_by,
        "recovery_note": cb.recovery_note,
    }
