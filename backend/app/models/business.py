"""商业实体模型 - businesses"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import BigInteger, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, SoftDeleteMixin, UUIDMixin
from app.database import Base


class Business(Base, TimestampMixin, SoftDeleteMixin, UUIDMixin):
    """商业实体/商户"""

    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    sub_category: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    business_model: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    province: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai")
    currency: Mapped[str] = mapped_column(String(16), nullable=False, default="CNY")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    owner_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    agent_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("agents.id"), nullable=True
    )
    config: Mapped[Optional[dict]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))

    # 关系
    member_roles: Mapped[List["UserBusinessRole"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    products: Mapped[List["Product"]] = relationship(back_populates="business", foreign_keys="[Product.business_id]")
    skus: Mapped[List["SKU"]] = relationship(back_populates="business", foreign_keys="[SKU.business_id]")
    orders: Mapped[List["Order"]] = relationship(back_populates="business", foreign_keys="[Order.business_id]")
    customers: Mapped[List["Customer"]] = relationship(back_populates="business", foreign_keys="[Customer.business_id]")
    agents: Mapped[List["Agent"]] = relationship(back_populates="business", foreign_keys="[Agent.business_id]")

    __table_args__ = (
        Index("idx_businesses_owner_id", "owner_id"),
        Index("idx_businesses_status", "status"),
        Index("idx_businesses_category", "category"),
        Index("idx_businesses_deleted_at", "deleted_at"),
    )
