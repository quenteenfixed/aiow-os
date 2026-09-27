"""运营表组 - alerts, audit_logs, circuit_breaks"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Alert(Base):
    """告警"""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    level: Mapped[str] = mapped_column(String(8), nullable=False, default="P2")
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    resolved_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        Index("idx_alerts_biz_status_level", "business_id", "status", "level"),
        Index("idx_alerts_biz_created", "business_id", "created_at"),
        Index("idx_alerts_alert_type", "alert_type"),
        Index("idx_alerts_level", "level"),
    )


class AuditLog(Base):
    """审计日志 - 不可篡改，链式哈希"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    before_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    after_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    log_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        Index("idx_audit_logs_biz_created", "business_id", "created_at"),
        Index("idx_audit_logs_actor", "actor_type", "actor_id"),
        Index("idx_audit_logs_action", "action"),
        Index("idx_audit_logs_target", "target_type", "target_id"),
        Index("idx_audit_logs_created_at", "created_at"),
    )


class CircuitBreak(Base):
    """熔断记录"""

    __tablename__ = "circuit_breaks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    # agent 级熔断指向的 Agent ID；system 级为 NULL
    agent_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(256), nullable=False)
    trigger_condition: Mapped[str] = mapped_column(String(128), nullable=False)
    trigger_value: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    threshold: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    recovered_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    recovered_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    recovery_note: Mapped[Optional[str]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        Index("idx_circuit_breaks_biz_status", "business_id", "status"),
        Index("idx_circuit_breaks_level_created", "level", "created_at"),
        Index("idx_circuit_breaks_created_at", "created_at"),
        # agent 级熔断精确查询索引（system 级 agent_id 为 NULL）
        Index("idx_circuit_breaks_biz_agent_status", "business_id", "agent_id", "status"),
    )
