"""OUPDEL 自主运营循环模型 - agent_loops, agent_loop_runs

M3-3 范围：
- agent_loops  : 每个 Agent 一份循环配置（频率、灵敏度、启用/停用）
- agent_loop_runs : 每次循环的完整运行记录（OUPDEL 各步骤产物）

OUPDEL = Observe + Understand + Plan + Decide + Execute + Learn
  1. Observe  : 采集关键指标（库存/销售/临期）
  2. Understand: 异常检测（库存过低/销量骤降/临期过多）
  3. Plan     : 针对异常生成解决方案
  4. Decide   : 风险评估，标注风险等级，决定是否执行
  5. Execute  : 创建工单（高风险仍需人工审批，低风险可自动执行）
  6. Learn    : 追踪效果，写入记忆（M4-1 落地后接入）
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger, Boolean, ForeignKey, Index, Integer, SmallInteger, String, text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin
from app.database import Base


class AgentLoop(Base, TimestampMixin):
    """Agent 自主运营循环配置（每个 Agent 一份）"""

    __tablename__ = "agent_loops"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="default_loop")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 触发频率（分钟），最小 5 分钟，默认 60 分钟（每小时一次）
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    # 灵敏度：low / medium / high，灵敏度越高阈值越低，越容易触发异常
    sensitivity: Mapped[str] = mapped_column(String(8), nullable=False, default="medium")
    # 自主级别 L0~L4：L0 全人工 / L1 建议 / L2 低风险自动 / L3 中风险自动 / L4 全自动
    autonomy_level: Mapped[str] = mapped_column(String(8), nullable=False, default="L2")
    # 自定义配置：阈值覆盖、跳过的检测项等
    config: Mapped[Optional[dict]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    last_run_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # 关系
    runs: Mapped[List["AgentLoopRun"]] = relationship(
        back_populates="loop", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("uk_agent_loops_agent_id", "agent_id", unique=True),
        Index("idx_agent_loops_biz_enabled", "business_id", "enabled"),
        Index("idx_agent_loops_next_run", "next_run_at"),
    )


class AgentLoopRun(Base):
    """单次循环运行记录（OUPDEL 各步骤产物完整保存）"""

    __tablename__ = "agent_loop_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    loop_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agent_loops.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id"), nullable=False
    )
    # 触发方式：scheduled（定时）/ manual（手动）/ test（测试）
    trigger_type: Mapped[str] = mapped_column(String(16), nullable=False, default="scheduled")
    # 运行状态：running / completed / failed / skipped
    run_status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # O - Observe 采集的原始指标
    observe_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # U - Understand 检测到的异常列表 [{type, severity, detail, ...}]
    anomalies: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    anomaly_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # P - Plan 针对异常生成的解决方案列表
    plans: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # D - Decide 风险评估后的最终决策（含风险等级与是否自动执行）
    decisions: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # E - Execute 创建的工单 ID 列表
    work_order_ids: Mapped[Optional[list]] = mapped_column(
        ARRAY(BigInteger), server_default=text("'{}'")
    )
    work_order_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # L - Learn 评估结果（追踪已执行工单的效果）
    evaluation: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    error_message: Mapped[Optional[str]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )

    # 关系
    loop: Mapped["AgentLoop"] = relationship(back_populates="runs")

    __table_args__ = (
        Index("idx_agent_loop_runs_loop_created", "loop_id", "created_at"),
        Index("idx_agent_loop_runs_biz_status", "business_id", "run_status"),
        Index("idx_agent_loop_runs_agent_created", "agent_id", "created_at"),
        Index("idx_agent_loop_runs_run_status", "run_status"),
    )
