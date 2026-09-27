"""用户与权限模型 - users, user_business_roles"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import BigInteger, ForeignKey, Index, String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, SoftDeleteMixin, UUIDMixin
from app.database import Base


class User(Base, TimestampMixin, SoftDeleteMixin, UUIDMixin):
    """用户表 - 跨商户共享"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    avatar: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    # 关系
    business_roles: Mapped[List["UserBusinessRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("uk_users_email", "email", unique=True, postgresql_where="email IS NOT NULL AND deleted_at IS NULL"),
        Index("uk_users_phone", "phone", unique=True, postgresql_where="phone IS NOT NULL AND deleted_at IS NULL"),
        Index("idx_users_status", "status"),
        Index("idx_users_deleted_at", "deleted_at"),
    )


class UserBusinessRole(Base, TimestampMixin):
    """用户-商户-角色关系"""

    __tablename__ = "user_business_roles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    # 关系
    user: Mapped["User"] = relationship(back_populates="business_roles")
    business: Mapped["Business"] = relationship(back_populates="member_roles")

    __table_args__ = (
        Index("uk_user_biz_roles_user_biz", "user_id", "business_id", unique=True),
        Index("idx_user_biz_roles_biz_role", "business_id", "role"),
        Index("idx_user_biz_roles_user_id", "user_id"),
        Index("idx_user_biz_roles_status", "status"),
    )
