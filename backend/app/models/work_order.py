"""工单模型 - work_orders, approval_actions, execution_jobs"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import BigInteger, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin
from app.database import Base


class WorkOrder(Base, TimestampMixin):
    """运营工单 - Agent 发起的操作任务"""

    __tablename__ = "work_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id"), nullable=False
    )
    order_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(nullable=True)
    expected_effect: Mapped[Optional[str]] = mapped_column(nullable=True)
    risk_level: Mapped[str] = mapped_column(String(8), nullable=False, default="medium")
    params: Mapped[Optional[dict]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    submitter_agent_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("agents.id"), nullable=True
    )
    approver_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # 关系
    approval_actions: Mapped[List["ApprovalAction"]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan"
    )
    execution_job: Mapped[Optional["ExecutionJob"]] = relationship(
        back_populates="work_order", uselist=False
    )

    __table_args__ = (
        Index("idx_work_orders_biz_status", "business_id", "status"),
        Index("idx_work_orders_agent_created", "agent_id", "created_at"),
        Index("idx_work_orders_status_created", "status", "created_at"),
        Index("idx_work_orders_order_type", "order_type"),
        Index("idx_work_orders_risk_level", "risk_level"),
    )


class ApprovalAction(Base):
    """审批动作记录"""

    __tablename__ = "approval_actions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    work_order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False
    )
    approver_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(nullable=True)
    modified_params: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )

    # 关系
    work_order: Mapped["WorkOrder"] = relationship(back_populates="approval_actions")

    __table_args__ = (
        Index("idx_approval_actions_work_order_created", "work_order_id", "created_at"),
        Index("idx_approval_actions_approver", "approver_id"),
        Index("idx_approval_actions_action", "action"),
    )


class ExecutionJob(Base):
    """执行任务"""

    __tablename__ = "execution_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    work_order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("work_orders.id"), nullable=False, unique=True
    )
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    result: Mapped[Optional[str]] = mapped_column(nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )

    # 关系
    work_order: Mapped["WorkOrder"] = relationship(back_populates="execution_job")

    __table_args__ = (
        Index("idx_execution_jobs_biz_status", "business_id", "status"),
        Index("idx_execution_jobs_agent_created", "agent_id", "created_at"),
        Index("idx_execution_jobs_status", "status"),
    )
