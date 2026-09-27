"""告警服务 - 生成、分级、去重/聚合、确认、解决

设计要点：
1. 多租户隔离：所有查询带 business_id
2. 去重：相同 business_id + alert_type + title + level 在 dedup_window 内不重复创建
3. 告警状态机：active → acknowledged → resolved（终态）
4. 告警记录不可删除（只写 + 软状态变更）
5. 告警级别：P0 紧急 / P1 重要 / P2 一般 / P3 提示
6. 告警类型：inventory（库存）/ sales（销售）/ expiring（临期）/ system（系统）
"""
import logging
from datetime import timedelta
from typing import Optional, Tuple

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.types import utcnow_naive
from app.models.operations import Alert

logger = logging.getLogger(__name__)


# ===== 序列化 =====

def _alert_dict(a: Alert) -> dict:
    return {
        "id": a.id,
        "business_id": a.business_id,
        "alert_type": a.alert_type,
        "level": a.level,
        "title": a.title,
        "content": a.content,
        "source": a.source,
        "status": a.status,
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


# ===== 创建（含去重）=====

async def _create_alert_no_commit(
    db: AsyncSession,
    business_id: int,
    alert_type: str,
    level: str,
    title: str,
    content: Optional[str] = None,
    source: str = "system",
    dedup_window_hours: int = 24,
) -> Alert:
    """创建告警但不提交（调用方管理事务）

    与 create_alert 不同：
    - 不返回 (alert, status) tuple，直接返回 Alert 对象（去重时返回现有记录）
    - 不调用 db.commit()，由调用方统一提交
    - 校验失败抛 ValueError 而非返回错误（更明确）
    """
    valid_types = {"inventory", "sales", "expiring", "system", "agent", "security", "circuit_breaker"}
    if alert_type not in valid_types:
        raise ValueError(f"非法告警类型：{alert_type}（应为 {valid_types}）")

    valid_levels = {"P0", "P1", "P2", "P3"}
    if level not in valid_levels:
        raise ValueError(f"非法告警级别：{level}（应为 {valid_levels}）")

    # 去重：找到最近窗口内同 type+title+level 的 active/acknowledged 记录
    if dedup_window_hours > 0:
        window_start = utcnow_naive() - timedelta(hours=dedup_window_hours)
        dup_stmt = select(Alert).where(
            Alert.business_id == business_id,
            Alert.alert_type == alert_type,
            Alert.title == title,
            Alert.level == level,
            Alert.status.in_(("active", "acknowledged")),
            Alert.created_at >= window_start,
        ).limit(1)
        existing = (await db.execute(dup_stmt)).scalar_one_or_none()
        if existing:
            logger.info(
                f"[AlertService] 告警去重：biz={business_id} type={alert_type} title={title[:30]}..."
            )
            return existing

    alert = Alert(
        business_id=business_id,
        alert_type=alert_type,
        level=level,
        title=title,
        content=content,
        source=source,
        status="active",
    )
    db.add(alert)
    await db.flush()
    logger.info(
        f"[AlertService] 创建告警 {alert.id}（type={alert_type}, level={level}, biz={business_id}）"
    )
    return alert


async def create_alert(
    db: AsyncSession,
    business_id: int,
    alert_type: str,
    level: str,
    title: str,
    content: Optional[str] = None,
    source: str = "system",
    dedup_window_hours: int = 24,
) -> Tuple[Optional[Alert], Optional[str]]:
    """创建告警（带去重）

    Returns:
        (alert, status) — alert 为 None 表示因校验失败，status 返回错误说明
        alert 为新建/已存在告警，status="created" / "deduplicated"
    """
    try:
        alert = await _create_alert_no_commit(
            db, business_id,
            alert_type=alert_type,
            level=level,
            title=title,
            content=content,
            source=source,
            dedup_window_hours=dedup_window_hours,
        )
    except ValueError as e:
        return None, str(e)

    # 判断是否新建（去重时返回的是已有记录，status 不同）
    is_new = alert.created_at is not None and (
        utcnow_naive() - alert.created_at
    ).total_seconds() < 5  # 5 秒内创建视为新建
    if not is_new:
        return alert, "deduplicated"

    await db.commit()
    await db.refresh(alert)
    return alert, "created"


async def create_alerts_batch(
    db: AsyncSession,
    business_id: int,
    alerts_data: list,
    dedup_window_hours: int = 24,
) -> dict:
    """批量创建告警（来自 OUPDEL observer 的异常列表）

    Args:
        alerts_data: [{"alert_type": "inventory", "level": "P1", "title": "...", "content": "...", "source": "loop"}, ...]

    Returns:
        {"created": N, "deduplicated": M, "errors": [...]}
    """
    created = 0
    deduplicated = 0
    errors = []

    for item in alerts_data:
        alert, status = await create_alert(
            db, business_id,
            alert_type=item.get("alert_type", "system"),
            level=item.get("level", "P2"),
            title=item.get("title", ""),
            content=item.get("content"),
            source=item.get("source", "loop"),
            dedup_window_hours=dedup_window_hours,
        )
        if status == "created":
            created += 1
        elif status == "deduplicated":
            deduplicated += 1
        else:
            errors.append({"title": item.get("title"), "error": status})

    logger.info(
        f"[AlertService] 批量创建告警：created={created} dedup={deduplicated} errors={len(errors)}"
    )
    return {"created": created, "deduplicated": deduplicated, "errors": errors}


# ===== 查询 =====

async def list_alerts(
    db: AsyncSession,
    business_id: int,
    status: Optional[str] = None,
    level: Optional[str] = None,
    alert_type: Optional[str] = None,
    source: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[list, int]:
    """告警列表（支持多维度筛选）"""
    stmt = select(Alert).where(Alert.business_id == business_id)
    if status:
        stmt = stmt.where(Alert.status == status)
    if level:
        stmt = stmt.where(Alert.level == level)
    if alert_type:
        stmt = stmt.where(Alert.alert_type == alert_type)
    if source:
        stmt = stmt.where(Alert.source == source)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(Alert.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = [_alert_dict(a) for a in (await db.execute(stmt)).scalars().all()]
    return items, total


async def get_alert(
    db: AsyncSession, business_id: int, alert_id: int
) -> Optional[Alert]:
    stmt = select(Alert).where(
        Alert.id == alert_id,
        Alert.business_id == business_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_alert_stats(
    db: AsyncSession, business_id: int
) -> dict:
    """告警统计：按 status 和 level 聚合"""
    # 按状态统计
    status_stmt = (
        select(Alert.status, func.count(Alert.id))
        .where(Alert.business_id == business_id)
        .group_by(Alert.status)
    )
    status_rows = (await db.execute(status_stmt)).all()
    status_distribution = {row[0]: row[1] for row in status_rows}
    for s in ("active", "acknowledged", "resolved"):
        status_distribution.setdefault(s, 0)

    # 按级别统计（仅 active + acknowledged）
    level_stmt = (
        select(Alert.level, func.count(Alert.id))
        .where(
            Alert.business_id == business_id,
            Alert.status.in_(("active", "acknowledged")),
        )
        .group_by(Alert.level)
    )
    level_rows = (await db.execute(level_stmt)).all()
    level_distribution = {row[0]: row[1] for row in level_rows}
    for lvl in ("P0", "P1", "P2", "P3"):
        level_distribution.setdefault(lvl, 0)

    # 按类型统计（仅 active + acknowledged）
    type_stmt = (
        select(Alert.alert_type, func.count(Alert.id))
        .where(
            Alert.business_id == business_id,
            Alert.status.in_(("active", "acknowledged")),
        )
        .group_by(Alert.alert_type)
    )
    type_rows = (await db.execute(type_stmt)).all()
    type_distribution = {row[0]: row[1] for row in type_rows}
    for t in ("inventory", "sales", "expiring", "system", "agent", "security"):
        type_distribution.setdefault(t, 0)

    return {
        "status_distribution": status_distribution,
        "level_distribution": level_distribution,
        "type_distribution": type_distribution,
        "total_active": status_distribution.get("active", 0),
        "total_acknowledged": status_distribution.get("acknowledged", 0),
        "total_resolved": status_distribution.get("resolved", 0),
    }


# ===== 状态机 =====

async def acknowledge_alert(
    db: AsyncSession,
    business_id: int,
    alert_id: int,
    user_id: int,
    comment: Optional[str] = None,
) -> Tuple[Optional[Alert], Optional[str]]:
    """确认告警：active → acknowledged"""
    alert = await get_alert(db, business_id, alert_id)
    if alert is None:
        return None, "告警不存在或无权访问"

    if alert.status != "active":
        return None, f"告警当前状态为 {alert.status}，无法确认（仅 active 可确认）"

    alert.status = "acknowledged"
    # 把确认人 comment 追加到 content
    if comment:
        prefix = f"\n\n[确认备注 by user={user_id}]: {comment}"
        alert.content = (alert.content or "") + prefix
    await db.commit()
    await db.refresh(alert)
    logger.info(f"[AlertService] 告警 {alert.id} 已确认（user={user_id}）")
    return alert, None


async def resolve_alert(
    db: AsyncSession,
    business_id: int,
    alert_id: int,
    user_id: int,
    comment: Optional[str] = None,
) -> Tuple[Optional[Alert], Optional[str]]:
    """解决告警：active/acknowledged → resolved"""
    alert = await get_alert(db, business_id, alert_id)
    if alert is None:
        return None, "告警不存在或无权访问"

    if alert.status not in ("active", "acknowledged"):
        return None, f"告警当前状态为 {alert.status}，无法解决"

    alert.status = "resolved"
    alert.resolved_at = utcnow_naive()
    if comment:
        prefix = f"\n\n[解决备注 by user={user_id}]: {comment}"
        alert.content = (alert.content or "") + prefix
    await db.commit()
    await db.refresh(alert)
    logger.info(f"[AlertService] 告警 {alert.id} 已解决（user={user_id}）")
    return alert, None
