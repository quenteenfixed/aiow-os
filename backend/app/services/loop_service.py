"""OUPDEL 循环服务 - 配置 CRUD + 运行记录 CRUD

设计要点：
1. 多租户隔离：所有查询带 business_id
2. 每个 Agent 一份循环配置（uk_agent_loops_agent_id）
3. Agent 创建时自动创建默认循环配置（enabled=false，避免立即触发）
4. 运行记录只写不改：状态从 running → completed/failed/skipped
"""
import logging
from typing import Optional, Tuple

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.types import utcnow_naive
from app.models.loop import AgentLoop, AgentLoopRun

logger = logging.getLogger(__name__)


# ===== 序列化 =====

def _loop_dict(loop: AgentLoop) -> dict:
    return {
        "id": loop.id,
        "business_id": loop.business_id,
        "agent_id": loop.agent_id,
        "name": loop.name,
        "enabled": loop.enabled,
        "interval_minutes": loop.interval_minutes,
        "sensitivity": loop.sensitivity,
        "autonomy_level": loop.autonomy_level,
        "config": loop.config or {},
        "last_run_at": loop.last_run_at.isoformat() if loop.last_run_at else None,
        "next_run_at": loop.next_run_at.isoformat() if loop.next_run_at else None,
        "created_at": loop.created_at.isoformat() if loop.created_at else None,
        "updated_at": loop.updated_at.isoformat() if loop.updated_at else None,
    }


def _run_dict(run: AgentLoopRun) -> dict:
    return {
        "id": run.id,
        "loop_id": run.loop_id,
        "business_id": run.business_id,
        "agent_id": run.agent_id,
        "trigger_type": run.trigger_type,
        "run_status": run.run_status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "duration_ms": run.duration_ms,
        "observe_data": run.observe_data,
        "anomalies": run.anomalies,
        "anomaly_count": run.anomaly_count,
        "plans": run.plans,
        "decisions": run.decisions,
        "work_order_ids": run.work_order_ids or [],
        "work_order_count": run.work_order_count,
        "evaluation": run.evaluation,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


# ===== 内部辅助 =====

async def _get_loop_by_id(
    db: AsyncSession, business_id: int, loop_id: int
) -> Optional[AgentLoop]:
    stmt = select(AgentLoop).where(
        AgentLoop.id == loop_id,
        AgentLoop.business_id == business_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _get_loop_by_agent_id(
    db: AsyncSession, business_id: int, agent_id: int
) -> Optional[AgentLoop]:
    stmt = select(AgentLoop).where(
        AgentLoop.agent_id == agent_id,
        AgentLoop.business_id == business_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


# ===== 循环配置 CRUD =====

async def create_loop(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    name: str = "default_loop",
    enabled: bool = False,
    interval_minutes: int = 60,
    sensitivity: str = "medium",
    autonomy_level: str = "L2",
    config: Optional[dict] = None,
) -> AgentLoop:
    """创建循环配置（每个 Agent 只能有一份）"""
    loop = AgentLoop(
        business_id=business_id,
        agent_id=agent_id,
        name=name,
        enabled=enabled,
        interval_minutes=interval_minutes,
        sensitivity=sensitivity,
        autonomy_level=autonomy_level,
        config=config or {},
    )
    db.add(loop)
    await db.commit()
    await db.refresh(loop)
    logger.info(
        f"[LoopService] 创建循环配置 {loop.id}（agent={agent_id}, interval={interval_minutes}min）"
    )
    return loop


async def list_loops(
    db: AsyncSession,
    business_id: int,
    agent_id: Optional[int] = None,
    enabled: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[list, int]:
    """循环配置列表"""
    stmt = select(AgentLoop).where(AgentLoop.business_id == business_id)
    if agent_id is not None:
        stmt = stmt.where(AgentLoop.agent_id == agent_id)
    if enabled is not None:
        stmt = stmt.where(AgentLoop.enabled == enabled)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(AgentLoop.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = [_loop_dict(loop) for loop in (await db.execute(stmt)).scalars().all()]
    return items, total


async def get_loop(db: AsyncSession, business_id: int, loop_id: int) -> Optional[AgentLoop]:
    return await _get_loop_by_id(db, business_id, loop_id)


async def get_or_create_loop(
    db: AsyncSession, business_id: int, agent_id: int
) -> AgentLoop:
    """获取或创建循环配置（默认 enabled=false，需手动启用）"""
    loop = await _get_loop_by_agent_id(db, business_id, agent_id)
    if loop is None:
        loop = await create_loop(db, business_id, agent_id)
    return loop


async def update_loop(
    db: AsyncSession,
    business_id: int,
    loop_id: int,
    *,
    name: Optional[str] = None,
    enabled: Optional[bool] = None,
    interval_minutes: Optional[int] = None,
    sensitivity: Optional[str] = None,
    autonomy_level: Optional[str] = None,
    config: Optional[dict] = None,
) -> Tuple[Optional[AgentLoop], Optional[str]]:
    """更新循环配置"""
    loop = await _get_loop_by_id(db, business_id, loop_id)
    if loop is None:
        return None, "循环配置不存在或无权访问"

    if name is not None:
        loop.name = name
    if enabled is not None:
        loop.enabled = enabled
        if not enabled:
            # 暂停时清空下次运行时间
            loop.next_run_at = None
    if interval_minutes is not None:
        if interval_minutes < 5:
            return None, "触发频率最小 5 分钟"
        loop.interval_minutes = interval_minutes
    if sensitivity is not None:
        if sensitivity not in ("low", "medium", "high"):
            return None, "灵敏度取值：low/medium/high"
        loop.sensitivity = sensitivity
    if autonomy_level is not None:
        if autonomy_level not in ("L0", "L1", "L2", "L3", "L4"):
            return None, "自主级别取值：L0/L1/L2/L3/L4"
        loop.autonomy_level = autonomy_level
    if config is not None:
        loop.config = config

    await db.commit()
    await db.refresh(loop)
    logger.info(f"[LoopService] 更新循环配置 {loop.id}")
    return loop, None


# ===== 运行记录 CRUD =====

async def create_run(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    loop_id: int,
    trigger_type: str = "scheduled",
) -> AgentLoopRun:
    """创建运行记录（run_status=running）

    started_at 显式写入 Python 端 UTC 时间，避免依赖 DB server_default（DB 时区可能不一致）
    """
    started_at = utcnow_naive()
    run = AgentLoopRun(
        loop_id=loop_id,
        business_id=business_id,
        agent_id=agent_id,
        trigger_type=trigger_type,
        run_status="running",
        started_at=started_at,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    logger.info(f"[LoopService] 创建运行记录 {run.id}（loop={loop_id}, trigger={trigger_type}）")
    return run


async def update_run(
    db: AsyncSession,
    business_id: int,
    run_id: int,
    *,
    run_status: Optional[str] = None,
    observe_data: Optional[dict] = None,
    anomalies: Optional[list] = None,
    anomaly_count: Optional[int] = None,
    plans: Optional[list] = None,
    decisions: Optional[list] = None,
    work_order_ids: Optional[list] = None,
    work_order_count: Optional[int] = None,
    evaluation: Optional[dict] = None,
    error_message: Optional[str] = None,
) -> Tuple[Optional[AgentLoopRun], Optional[str]]:
    """更新运行记录（各步骤产物）"""
    stmt = select(AgentLoopRun).where(
        AgentLoopRun.id == run_id,
        AgentLoopRun.business_id == business_id,
    )
    run = (await db.execute(stmt)).scalar_one_or_none()
    if run is None:
        return None, "运行记录不存在或无权访问"

    if observe_data is not None:
        run.observe_data = observe_data
    if anomalies is not None:
        run.anomalies = anomalies
    if anomaly_count is not None:
        run.anomaly_count = anomaly_count
    if plans is not None:
        run.plans = plans
    if decisions is not None:
        run.decisions = decisions
    if work_order_ids is not None:
        run.work_order_ids = work_order_ids
    if work_order_count is not None:
        run.work_order_count = work_order_count
    if evaluation is not None:
        run.evaluation = evaluation
    if error_message is not None:
        run.error_message = error_message
    if run_status is not None:
        if run_status not in ("running", "completed", "failed", "skipped"):
            return None, "非法运行状态"
        run.run_status = run_status
        if run_status in ("completed", "failed", "skipped"):
            run.completed_at = utcnow_naive()
            if run.started_at:
                delta = run.completed_at - run.started_at
                run.duration_ms = int(delta.total_seconds() * 1000)

    await db.commit()
    await db.refresh(run)
    return run, None


async def list_runs(
    db: AsyncSession,
    business_id: int,
    loop_id: Optional[int] = None,
    agent_id: Optional[int] = None,
    run_status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[list, int]:
    """运行记录列表"""
    stmt = select(AgentLoopRun).where(AgentLoopRun.business_id == business_id)
    if loop_id is not None:
        stmt = stmt.where(AgentLoopRun.loop_id == loop_id)
    if agent_id is not None:
        stmt = stmt.where(AgentLoopRun.agent_id == agent_id)
    if run_status is not None:
        stmt = stmt.where(AgentLoopRun.run_status == run_status)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(AgentLoopRun.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = [_run_dict(run) for run in (await db.execute(stmt)).scalars().all()]
    return items, total


async def get_run(
    db: AsyncSession, business_id: int, run_id: int
) -> Optional[AgentLoopRun]:
    stmt = select(AgentLoopRun).where(
        AgentLoopRun.id == run_id,
        AgentLoopRun.business_id == business_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def mark_loop_run(
    db: AsyncSession, business_id: int, loop_id: int, started_at=None
) -> None:
    """更新循环配置的 last_run_at / next_run_at"""
    loop = await _get_loop_by_id(db, business_id, loop_id)
    if loop is None:
        return
    now = utcnow_naive()
    loop.last_run_at = started_at or now
    # 计算下次运行时间
    from datetime import timedelta
    loop.next_run_at = loop.last_run_at + timedelta(minutes=loop.interval_minutes)
    await db.commit()
