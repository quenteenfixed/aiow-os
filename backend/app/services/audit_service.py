"""审计服务 - M5-3 / M6-3 修复版

M6-3 修复要点：
1. _get_last_hash 加 SELECT ... FOR UPDATE 行锁，避免并发写入导致哈希链断裂
2. record_audit 拆分为 _record_audit_no_commit（不提交，调用方管理事务）+ record_audit（自带提交）
3. list_audit_logs 转义 LIKE 通配符 % _，避免模糊匹配越权
"""
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.types import utcnow_naive
from app.models.operations import AuditLog

logger = logging.getLogger(__name__)


# ===== 哈希链 =====

def _compute_hash(
    prev_hash: str,
    business_id: int,
    actor_type: str,
    actor_id: Optional[int],
    action: str,
    target_type: str,
    target_id: Optional[int],
    created_at: datetime,
) -> str:
    """计算审计记录哈希（链式哈希）

    raw 字段顺序与 verify_chain 保持一致；任何字段变更都会导致后续所有 hash 失效。
    """
    raw = "|".join([
        prev_hash,
        str(business_id),
        actor_type,
        str(actor_id or ""),
        action,
        target_type,
        str(target_id or ""),
        created_at.isoformat(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _get_last_hash_for_update(db: AsyncSession, business_id: int) -> str:
    """获取上一条审计记录的 hash，并对该行加锁（FOR UPDATE）

    通过行锁串行化同 business_id 的并发写入，保证哈希链连续性。
    无记录时返回 "0"*64（占位前向哈希）。
    """
    stmt = (
        select(AuditLog)
        .where(AuditLog.business_id == business_id)
        .order_by(AuditLog.id.desc())
        .limit(1)
        .with_for_update()
    )
    result = await db.execute(stmt)
    last = result.scalars().first()
    return last.log_hash if last else "0" * 64


async def _get_last_hash(db: AsyncSession, business_id: int) -> str:
    """获取上一条审计记录的 hash（不加锁，用于校验/查询）"""
    stmt = select(AuditLog.log_hash).where(
        AuditLog.business_id == business_id,
    ).order_by(AuditLog.id.desc()).limit(1)
    result = await db.execute(stmt)
    last = result.scalar_one_or_none()
    return last if last else "0" * 64


# ===== 记录审计 =====

async def _record_audit_no_commit(
    db: AsyncSession,
    business_id: int,
    actor_type: str,
    action: str,
    target_type: str,
    target_id: Optional[int] = None,
    actor_id: Optional[int] = None,
    before_data: Optional[dict] = None,
    after_data: Optional[dict] = None,
    reason: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    """记录审计日志但不提交（调用方负责 commit/rollback）

    使用前请确保 db 已开启事务（默认即处于事务中）。
    """
    now = utcnow_naive()
    prev_hash = await _get_last_hash_for_update(db, business_id)
    log_hash = _compute_hash(
        prev_hash, business_id, actor_type, actor_id,
        action, target_type, target_id, now,
    )

    log = AuditLog(
        business_id=business_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_data=before_data,
        after_data=after_data,
        reason=reason,
        ip_address=ip_address,
        user_agent=user_agent,
        log_hash=log_hash,
        created_at=now,
    )
    db.add(log)
    await db.flush()  # 让调用方能拿到 log.id，但不提交
    return log


async def record_audit(
    db: AsyncSession,
    business_id: int,
    actor_type: str,
    action: str,
    target_type: str,
    target_id: Optional[int] = None,
    actor_id: Optional[int] = None,
    before_data: Optional[dict] = None,
    after_data: Optional[dict] = None,
    reason: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    """记录一条审计日志（自带提交）

    如需将审计写入与其他业务写入放在同一事务，请使用 _record_audit_no_commit。
    """
    log = await _record_audit_no_commit(
        db, business_id, actor_type, action, target_type,
        target_id=target_id, actor_id=actor_id,
        before_data=before_data, after_data=after_data,
        reason=reason, ip_address=ip_address, user_agent=user_agent,
    )
    await db.commit()
    await db.refresh(log)
    return log


# ===== 哈希链校验 =====

async def verify_chain(
    db: AsyncSession, business_id: int
) -> dict:
    """校验审计日志哈希链完整性

    Returns:
        {"valid": bool, "total": N, "broken_at": id or None, "broken_reason": "..."}
    """
    stmt = select(AuditLog).where(
        AuditLog.business_id == business_id,
    ).order_by(AuditLog.id.asc())
    logs = (await db.execute(stmt)).scalars().all()

    if not logs:
        return {"valid": True, "total": 0, "broken_at": None}

    prev_hash = "0" * 64
    for log in logs:
        expected = _compute_hash(
            prev_hash, log.business_id, log.actor_type, log.actor_id,
            log.action, log.target_type, log.target_id, log.created_at,
        )
        if expected != log.log_hash:
            return {
                "valid": False,
                "total": len(logs),
                "broken_at": log.id,
                "broken_reason": f"记录 #{log.id} 哈希不匹配",
            }
        prev_hash = log.log_hash

    return {"valid": True, "total": len(logs), "broken_at": None}


# ===== 审计查询 =====

def _escape_like(s: str) -> str:
    """转义 SQL LIKE 通配符 % _ \\，防止模糊匹配越权"""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_audit_logs(
    db: AsyncSession,
    business_id: int,
    actor_type: Optional[str] = None,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    actor_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple:
    """审计日志查询（多维度筛选 + 分页）

    action 参数支持模糊匹配，但已转义 % _ 通配符，避免越权查询。
    """
    stmt = select(AuditLog).where(AuditLog.business_id == business_id)
    if actor_type:
        stmt = stmt.where(AuditLog.actor_type == actor_type)
    if action:
        # 转义用户输入的 % _，再用 LIKE 模糊匹配
        escaped = _escape_like(action)
        stmt = stmt.where(AuditLog.action.ilike(f"%{escaped}%", escape="\\"))
    if target_type:
        stmt = stmt.where(AuditLog.target_type == target_type)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if start_date:
        stmt = stmt.where(AuditLog.created_at >= start_date)
    if end_date:
        stmt = stmt.where(AuditLog.created_at <= end_date)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    logs = (await db.execute(stmt)).scalars().all()

    items = [
        {
            "id": log.id,
            "actor_type": log.actor_type,
            "actor_id": log.actor_id,
            "action": log.action,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "before_data": log.before_data,
            "after_data": log.after_data,
            "reason": log.reason,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]
    return items, total


async def get_audit_stats(
    db: AsyncSession, business_id: int, days: int = 30
) -> dict:
    """审计统计"""
    start = utcnow_naive() - timedelta(days=days)
    stmt = select(AuditLog).where(
        AuditLog.business_id == business_id,
        AuditLog.created_at >= start,
    )
    logs = (await db.execute(stmt)).scalars().all()

    by_action = {}
    by_actor_type = {}
    for log in logs:
        by_action[log.action] = by_action.get(log.action, 0) + 1
        by_actor_type[log.actor_type] = by_actor_type.get(log.actor_type, 0) + 1

    return {
        "total": len(logs),
        "days": days,
        "by_action": by_action,
        "by_actor_type": by_actor_type,
    }
