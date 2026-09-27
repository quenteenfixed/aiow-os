"""客户模型"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, SoftDeleteMixin, UUIDMixin
from app.database import Base


class Customer(Base, TimestampMixin, SoftDeleteMixin, UUIDMixin):
    """客户档案"""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    avatar: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    tags: Mapped[Optional[list]] = mapped_column(ARRAY(String), server_default=text("'{}'"))
    total_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_amount: Mapped[Decimal] = mapped_column(nullable=False, default=Decimal("0.00"))
    last_order_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # 关系
    business: Mapped["Business"] = relationship(back_populates="customers")
    orders: Mapped[List["Order"]] = relationship(back_populates="customer")

    __table_args__ = (
        Index(
            "uk_customers_biz_phone", "business_id", "phone", unique=True,
            postgresql_where="phone IS NOT NULL AND deleted_at IS NULL",
        ),
        Index("idx_customers_biz_level", "business_id", "level"),
        Index("idx_customers_biz_last_order", "business_id", "last_order_at"),
        Index("idx_customers_deleted_at", "deleted_at"),
    )
