"""A2A 模型 - a2a_agents, a2a_sessions, a2a_messages, a2a_gateway_logs"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin
from app.database import Base


class A2AAgent(Base, TimestampMixin):
    """外部 Agent 接入"""

    __tablename__ = "a2a_agents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    developer: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    api_key_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    rate_limit_per_min: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    credit_level: Mapped[str] = mapped_column(String(16), nullable=False, default="standard")

    # 关系
    sessions: Mapped[List["A2ASession"]] = relationship(back_populates="external_agent")
    gateway_logs: Mapped[List["A2AGatewayLog"]] = relationship(back_populates="external_agent")

    __table_args__ = (
        Index("idx_a2a_agents_status", "status"),
        Index("idx_a2a_agents_credit_level", "credit_level"),
    )


class A2ASession(Base):
    """A2A 会话"""

    __tablename__ = "a2a_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    external_agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("a2a_agents.id"), nullable=False
    )
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    session_status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    started_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )

    # 关系
    external_agent: Mapped["A2AAgent"] = relationship(back_populates="sessions")
    messages: Mapped[List["A2AMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_a2a_sessions_external_biz", "external_agent_id", "business_id"),
        Index("idx_a2a_sessions_status_created", "session_status", "created_at"),
        Index("idx_a2a_sessions_business_id", "business_id"),
    )


class A2AMessage(Base):
    """A2A 消息"""

    __tablename__ = "a2a_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    a2a_session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("a2a_sessions.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    response_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )

    # 关系
    session: Mapped["A2ASession"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("idx_a2a_messages_session_created", "a2a_session_id", "created_at"),
        Index("idx_a2a_messages_message_type", "message_type"),
        Index("idx_a2a_messages_direction", "direction"),
    )


class A2AGatewayLog(Base):
    """A2A 网关日志 - 只追加"""

    __tablename__ = "a2a_gateway_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    external_agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("a2a_agents.id"), nullable=False
    )
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    endpoint: Mapped[str] = mapped_column(String(128), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    request_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    response_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )

    # 关系
    external_agent: Mapped["A2AAgent"] = relationship(back_populates="gateway_logs")

    __table_args__ = (
        Index("idx_a2a_gw_logs_external_created", "external_agent_id", "created_at"),
        Index("idx_a2a_gw_logs_biz_created", "business_id", "created_at"),
        Index("idx_a2a_gw_logs_status_code", "status_code"),
        Index("idx_a2a_gw_logs_created_at", "created_at"),
        Index("idx_a2a_gw_logs_request_hash", "request_hash"),
    )
