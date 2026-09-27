"""工单服务 - CRUD + 状态机 + 审批 + 执行

工单状态机：
  pending（待审批）
    → approved（已批准）  [审批通过]
    → rejected（已拒绝）  [审批拒绝]
    → cancelled（已取消） [主动取消]

  approved（已批准）
    → executing（执行中） [开始执行]
    → cancelled（已取消）

  executing（执行中）
    → completed（已完成） [执行成功]
    → failed（失败）       [执行失败]

设计要点：
1. 多租户隔离：所有查询带 business_id
2. 工单不可删除（软删除 / 只写），只能改状态
3. 审批记录写入 approval_actions 表
4. 执行结果写入 execution_jobs 表
5. 只有有权限的用户能审批（需 work_order:approve 权限）
"""
import logging
from typing import Optional, Tuple

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.types import utcnow_naive
from app.models.work_order import WorkOrder, ApprovalAction, ExecutionJob

logger = logging.getLogger(__name__)

# 合法的状态流转
VALID_TRANSITIONS = {
    "pending": {"approved", "rejected", "cancelled"},
    "approved": {"executing", "cancelled"},
    "executing": {"completed", "failed"},
    "completed": set(),   # 终态
    "rejected": set(),    # 终态
    "cancelled": set(),   # 终态
    "failed": set(),      # 终态
}


# ===== 序列化 =====

def _work_order_dict(wo: WorkOrder, include_relations: bool = True) -> dict:
    """工单序列化"""
    data = {
        "id": wo.id,
        "business_id": wo.business_id,
        "agent_id": wo.agent_id,
        "order_type": wo.order_type,
        "title": wo.title,
        "description": wo.description,
        "reason": wo.reason,
        "expected_effect": wo.expected_effect,
        "risk_level": wo.risk_level,
        "params": wo.params or {},
        "status": wo.status,
        "submitter_agent_id": wo.submitter_agent_id,
        "approver_id": wo.approver_id,
        "approved_at": wo.approved_at.isoformat() if wo.approved_at else None,
        "created_at": wo.created_at.isoformat() if wo.created_at else None,
        "updated_at": wo.updated_at.isoformat() if wo.updated_at else None,
    }
    if include_relations:
        data["approval_actions"] = [
            _approval_action_dict(a) for a in (wo.approval_actions or [])
        ]
        data["execution_job"] = (
            _execution_job_dict(wo.execution_job) if wo.execution_job else None
        )
    return data


def _approval_action_dict(a: ApprovalAction) -> dict:
    return {
        "id": a.id,
        "work_order_id": a.work_order_id,
        "approver_id": a.approver_id,
        "action": a.action,
        "comment": a.comment,
        "modified_params": a.modified_params,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _execution_job_dict(ej: ExecutionJob) -> dict:
    return {
        "id": ej.id,
        "work_order_id": ej.work_order_id,
        "business_id": ej.business_id,
        "agent_id": ej.agent_id,
        "status": ej.status,
        "result": ej.result,
        "error_message": ej.error_message,
        "started_at": ej.started_at.isoformat() if ej.started_at else None,
        "completed_at": ej.completed_at.isoformat() if ej.completed_at else None,
        "created_at": ej.created_at.isoformat() if ej.created_at else None,
    }


# ===== CRUD =====

async def create_work_order(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    order_type: str,
    title: str,
    reason: Optional[str] = None,
    description: Optional[str] = None,
    expected_effect: Optional[str] = None,
    risk_level: str = "medium",
    params: Optional[dict] = None,
    submitter_agent_id: Optional[int] = None,
) -> WorkOrder:
    """Agent 创建工单"""
    wo = WorkOrder(
        business_id=business_id,
        agent_id=agent_id,
        order_type=order_type,
        title=title,
        description=description,
        reason=reason,
        expected_effect=expected_effect,
        risk_level=risk_level,
        params=params or {},
        status="pending",
        submitter_agent_id=submitter_agent_id or agent_id,
    )
    db.add(wo)
    await db.commit()
    await db.refresh(wo)
    logger.info(
        f"[WorkOrderService] 创建工单 {wo.id}（type={order_type}, risk={risk_level}）"
    )
    return wo


async def list_work_orders(
    db: AsyncSession,
    business_id: int,
    status: Optional[str] = None,
    order_type: Optional[str] = None,
    risk_level: Optional[str] = None,
    agent_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[list, int]:
    """工单列表（支持按状态/类型/风险/Agent 筛选）"""
    stmt = select(WorkOrder).where(WorkOrder.business_id == business_id)
    if status:
        stmt = stmt.where(WorkOrder.status == status)
    if order_type:
        stmt = stmt.where(WorkOrder.order_type == order_type)
    if risk_level:
        stmt = stmt.where(WorkOrder.risk_level == risk_level)
    if agent_id:
        stmt = stmt.where(WorkOrder.agent_id == agent_id)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(WorkOrder.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = [_work_order_dict(wo, include_relations=False) for wo in result.scalars().all()]
    return items, total


async def get_work_order(
    db: AsyncSession,
    business_id: int,
    work_order_id: int,
) -> Optional[WorkOrder]:
    """获取工单详情（含审批历史 + 执行结果）"""
    stmt = (
        select(WorkOrder)
        .options(selectinload(WorkOrder.approval_actions))
        .options(selectinload(WorkOrder.execution_job))
        .where(
            WorkOrder.id == work_order_id,
            WorkOrder.business_id == business_id,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ===== 状态机 =====

async def approve_work_order(
    db: AsyncSession,
    business_id: int,
    work_order_id: int,
    approver_id: int,
    comment: Optional[str] = None,
    modified_params: Optional[dict] = None,
) -> Tuple[Optional[WorkOrder], Optional[str]]:
    """审批通过：pending → approved

    Returns:
        (work_order, error) — error 不为 None 时表示状态流转失败
    """
    wo = await _get_for_update(db, business_id, work_order_id)
    if wo is None:
        return None, "工单不存在或无权访问"

    if wo.status != "pending":
        return None, f"工单当前状态为 {wo.status}，无法审批（仅 pending 可审批）"

    wo.status = "approved"
    wo.approver_id = approver_id
    wo.approved_at = utcnow_naive()
    if modified_params:
        wo.params = {**(wo.params or {}), **modified_params}

    # 记录审批动作
    action = ApprovalAction(
        work_order_id=wo.id,
        approver_id=approver_id,
        action="approve",
        comment=comment,
        modified_params=modified_params,
    )
    db.add(action)
    await db.commit()
    await db.refresh(wo)

    # M4-2: 写入反馈记忆（批准）
    try:
        from app.services.feedback_service import record_approval_feedback
        await record_approval_feedback(
            db, wo.business_id, wo.agent_id, wo,
            action="approve", comment=comment, approver_id=approver_id,
        )
    except Exception as e:
        logger.warning(f"[WorkOrderService] 写入批准反馈失败：{e}")

    logger.info(f"[WorkOrderService] 工单 {wo.id} 审批通过（approver={approver_id}）")
    return wo, None


async def reject_work_order(
    db: AsyncSession,
    business_id: int,
    work_order_id: int,
    approver_id: int,
    comment: Optional[str] = None,
) -> Tuple[Optional[WorkOrder], Optional[str]]:
    """审批拒绝：pending → rejected"""
    wo = await _get_for_update(db, business_id, work_order_id)
    if wo is None:
        return None, "工单不存在或无权访问"

    if wo.status != "pending":
        return None, f"工单当前状态为 {wo.status}，无法拒绝（仅 pending 可拒绝）"

    wo.status = "rejected"
    wo.approver_id = approver_id
    wo.approved_at = utcnow_naive()

    action = ApprovalAction(
        work_order_id=wo.id,
        approver_id=approver_id,
        action="reject",
        comment=comment,
    )
    db.add(action)
    await db.commit()
    await db.refresh(wo)

    # M4-2: 写入反馈记忆（拒绝，高重要度）
    try:
        from app.services.feedback_service import record_approval_feedback
        await record_approval_feedback(
            db, wo.business_id, wo.agent_id, wo,
            action="reject", comment=comment, approver_id=approver_id,
        )
    except Exception as e:
        logger.warning(f"[WorkOrderService] 写入拒绝反馈失败：{e}")

    logger.info(f"[WorkOrderService] 工单 {wo.id} 审批拒绝（approver={approver_id}, reason={comment}）")
    return wo, None


async def cancel_work_order(
    db: AsyncSession,
    business_id: int,
    work_order_id: int,
    user_id: int,
    comment: Optional[str] = None,
) -> Tuple[Optional[WorkOrder], Optional[str]]:
    """取消工单：pending/approved → cancelled"""
    wo = await _get_for_update(db, business_id, work_order_id)
    if wo is None:
        return None, "工单不存在或无权访问"

    if wo.status not in ("pending", "approved"):
        return None, f"工单当前状态为 {wo.status}，无法取消"

    wo.status = "cancelled"

    action = ApprovalAction(
        work_order_id=wo.id,
        approver_id=user_id,
        action="cancel",
        comment=comment,
    )
    db.add(action)
    await db.commit()
    await db.refresh(wo)
    logger.info(f"[WorkOrderService] 工单 {wo.id} 已取消（user={user_id}）")
    return wo, None


async def start_execution(
    db: AsyncSession,
    business_id: int,
    work_order_id: int,
) -> Tuple[Optional[WorkOrder], Optional[str]]:
    """开始执行：approved → executing，创建 ExecutionJob 并自动执行

    M3-2：执行时自动调用对应写入工具的 handler，回写结果。
    """
    wo = await _get_for_update(db, business_id, work_order_id)
    if wo is None:
        return None, "工单不存在或无权访问"

    if wo.status != "approved":
        return None, f"工单当前状态为 {wo.status}，无法执行（仅 approved 可执行）"

    # 创建执行任务
    job = ExecutionJob(
        work_order_id=wo.id,
        business_id=business_id,
        agent_id=wo.agent_id,
        status="pending",
    )
    db.add(job)
    wo.status = "executing"
    await db.flush()
    job.status = "running"
    job.started_at = utcnow_naive()
    await db.flush()

    # 自动执行：调用对应写入工具的 handler
    is_success = True
    result_text = ""
    error_msg = None
    try:
        from app.agent.tools.write_tools import execute_work_order_handler
        result_text = await execute_work_order_handler(
            db, business_id, wo.agent_id, wo.order_type, wo.params or {},
        )
        await db.commit()
    except Exception as e:
        is_success = False
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"[WorkOrderService] 工单 {wo.id} 执行失败：{e}", exc_info=True)
        await db.rollback()
        # 重新获取 wo（rollback 后对象可能 expired）
        wo = await _get_for_update(db, business_id, work_order_id)
        if wo is None:
            return None, "工单执行失败后无法恢复"
        job = (await db.execute(
            select(ExecutionJob).where(ExecutionJob.work_order_id == wo.id)
        )).scalar_one_or_none()
        if job is None:
            job = ExecutionJob(
                work_order_id=wo.id, business_id=business_id,
                agent_id=wo.agent_id, status="running",
            )
            job.started_at = utcnow_naive()
            db.add(job)

    # 回写结果
    if job:
        job.result = result_text if is_success else None
        job.error_message = error_msg
        job.completed_at = utcnow_naive()
        job.status = "completed" if is_success else "failed"
    wo.status = "completed" if is_success else "failed"
    await db.commit()
    # 重新查询，eager load 关系
    wo = await get_work_order(db, business_id, wo.id)
    logger.info(
        f"[WorkOrderService] 工单 {wo.id} 执行{'完成' if is_success else '失败'}"
    )
    return wo, None


async def complete_execution(
    db: AsyncSession,
    business_id: int,
    work_order_id: int,
    result: str,
    is_success: bool = True,
    error_message: Optional[str] = None,
) -> Tuple[Optional[WorkOrder], Optional[str]]:
    """执行完成：executing → completed/failed，回写结果"""
    wo = await _get_for_update(db, business_id, work_order_id)
    if wo is None:
        return None, "工单不存在或无权访问"

    if wo.status != "executing":
        return None, f"工单当前状态为 {wo.status}，无法回写结果"

    # 更新 ExecutionJob
    stmt = select(ExecutionJob).where(ExecutionJob.work_order_id == wo.id)
    job = (await db.execute(stmt)).scalar_one_or_none()
    if job:
        job.result = result
        job.error_message = error_message
        job.completed_at = utcnow_naive()
        job.status = "completed" if is_success else "failed"

    wo.status = "completed" if is_success else "failed"
    await db.commit()
    # 重新查询，eager load 关系
    wo = await get_work_order(db, business_id, wo.id)
    logger.info(
        f"[WorkOrderService] 工单 {wo.id} 执行{'完成' if is_success else '失败'}"
    )
    return wo, None


async def _get_for_update(
    db: AsyncSession, business_id: int, work_order_id: int
) -> Optional[WorkOrder]:
    """查询工单（带 business_id 校验）"""
    stmt = select(WorkOrder).where(
        WorkOrder.id == work_order_id,
        WorkOrder.business_id == business_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
