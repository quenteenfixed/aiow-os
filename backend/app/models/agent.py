"""Agent 模型 - agents, agent_sessions, agent_messages, agent_memories, agent_skills"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin
from app.database import Base


class Agent(Base, TimestampMixin):
    """Agent 实例 - 每商户一个 Store Manager"""

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="store_manager")
    avatar: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    autonomy_level: Mapped[str] = mapped_column(String(8), nullable=False, default="L2")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="initializing")
    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    system_prompt_text: Mapped[Optional[str]] = mapped_column(nullable=True)
    config: Mapped[Optional[dict]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))

    # 关系
    business: Mapped["Business"] = relationship(back_populates="agents", foreign_keys="[Agent.business_id]")
    sessions: Mapped[List["AgentSession"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )
    memories: Mapped[List["AgentMemory"]] = relationship(back_populates="agent")
    skills: Mapped[List["AgentSkill"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "uk_agents_business_id", "business_id", unique=True,
            postgresql_where="status != 'stopped'",
        ),
        Index("idx_agents_status", "status"),
        Index("idx_agents_role", "role"),
        Index("idx_agents_autonomy_level", "autonomy_level"),
    )


class AgentSession(Base, TimestampMixin):
    """Agent 会话"""

    __tablename__ = "agent_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id"), nullable=False
    )
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    session_type: Mapped[str] = mapped_column(String(16), nullable=False, default="chat")
    title: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    context_summary: Mapped[Optional[str]] = mapped_column(nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # 关系
    agent: Mapped["Agent"] = relationship(back_populates="sessions")
    messages: Mapped[List["AgentMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_agent_sessions_agent_status", "agent_id", "status"),
        Index("idx_agent_sessions_biz_created", "business_id", "created_at"),
        Index("idx_agent_sessions_session_type", "session_type"),
    )


class AgentMessage(Base):
    """Agent 消息"""

    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(nullable=True)
    tool_calls: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    tool_call_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tool_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )

    # 关系
    session: Mapped["AgentSession"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("idx_agent_messages_session_created", "session_id", "created_at"),
        Index("idx_agent_messages_agent_created", "agent_id", "created_at"),
        Index("idx_agent_messages_role", "role"),
    )


class AgentMemory(Base, TimestampMixin):
    """Agent 记忆库"""

    __tablename__ = "agent_memories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id"), nullable=False
    )
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    memory_type: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(nullable=False)
    tags: Mapped[Optional[list]] = mapped_column(ARRAY(String), server_default=text("'{}'"))
    importance: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3)
    source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    source_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, server_default=text("'{}'::jsonb"))
    # M4-1: 过期时间，临时记忆自动过期；NULL 表示永久记忆
    expires_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # 关系
    agent: Mapped["Agent"] = relationship(back_populates="memories")

    __table_args__ = (
        Index("idx_agent_memories_agent_type_created", "agent_id", "memory_type", "created_at"),
        Index("idx_agent_memories_agent_importance", "agent_id", "importance"),
        Index("idx_agent_memories_source", "source", "source_id"),
        Index("idx_agent_memories_expires_at", "expires_at"),
    )


class AgentSkill(Base):
    """Agent 已安装 Skill"""

    __tablename__ = "agent_skills"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    skill_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="enabled")
    config: Mapped[Optional[dict]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    installed_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )

    # 关系
    agent: Mapped["Agent"] = relationship(back_populates="skills")

    __table_args__ = (
        Index("uk_agent_skills_agent_skill_key", "agent_id", "skill_key", unique=True),
        Index("idx_agent_skills_status", "status"),
    )
