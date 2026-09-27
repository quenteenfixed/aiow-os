"""订单模型 - orders, order_items"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, SoftDeleteMixin, UUIDMixin
from app.database import Base


class Order(Base, TimestampMixin, SoftDeleteMixin, UUIDMixin):
    """订单主表"""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    order_no: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    customer_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("customers.id"), nullable=True
    )
    customer_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    customer_phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(nullable=False, default=Decimal("0.00"))
    discount_amount: Mapped[Decimal] = mapped_column(nullable=False, default=Decimal("0.00"))
    payable_amount: Mapped[Decimal] = mapped_column(nullable=False, default=Decimal("0.00"))
    paid_amount: Mapped[Decimal] = mapped_column(nullable=False, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    payment_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unpaid")
    payment_method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    shipping_address: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    remark: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # 关系
    business: Mapped["Business"] = relationship(back_populates="orders")
    customer: Mapped[Optional["Customer"]] = relationship(back_populates="orders")
    items: Mapped[List["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_orders_business_id_status", "business_id", "status"),
        Index("idx_orders_customer_id", "customer_id"),
        Index("idx_orders_created_at", "created_at"),
        Index("idx_orders_biz_created", "business_id", "created_at"),
        Index("idx_orders_payment_status", "payment_status"),
        Index("idx_orders_deleted_at", "deleted_at"),
    )


class OrderItem(Base):
    """订单明细"""

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    sku_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("skus.id"), nullable=True
    )
    product_name: Mapped[str] = mapped_column(String(256), nullable=False)
    sku_spec: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(nullable=False)
    discount: Mapped[Decimal] = mapped_column(nullable=False, default=Decimal("0.00"))
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )

    # 关系
    order: Mapped["Order"] = relationship(back_populates="items")

    __table_args__ = (
        Index("idx_order_items_order_id", "order_id"),
        Index("idx_order_items_biz_sku", "business_id", "sku_id"),
        Index("idx_order_items_business_id", "business_id"),
    )
