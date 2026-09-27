"""库存模型 - inventory_logs, inventory_batches"""
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import BigInteger, Date, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin
from app.database import Base


class InventoryLog(Base):
    """库存流水 - 只追加，不更新不删除"""

    __tablename__ = "inventory_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    sku_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("skus.id"), nullable=False
    )
    change_type: Mapped[str] = mapped_column(String(16), nullable=False)
    change_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    before_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    after_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    ref_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    ref_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    operator_type: Mapped[str] = mapped_column(String(16), nullable=False)
    operator_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )

    # 关系
    sku: Mapped["SKU"] = relationship(back_populates="inventory_logs")

    __table_args__ = (
        Index("idx_inventory_logs_biz_sku_created", "business_id", "sku_id", "created_at"),
        Index("idx_inventory_logs_operator", "operator_type", "operator_id"),
        Index("idx_inventory_logs_ref", "ref_type", "ref_id"),
        Index("idx_inventory_logs_change_type", "change_type"),
    )


class InventoryBatch(Base, TimestampMixin):
    """库存批次 - FIFO + 保质期"""

    __tablename__ = "inventory_batches"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    sku_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("skus.id"), nullable=False
    )
    batch_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    supplier_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    in_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    in_date: Mapped[date] = mapped_column(Date, nullable=False)
    expire_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    # 关系
    sku: Mapped["SKU"] = relationship(back_populates="inventory_batches")

    __table_args__ = (
        Index("idx_inventory_batches_biz_sku", "business_id", "sku_id"),
        Index("idx_inventory_batches_expire_date", "expire_date"),
        Index("idx_inventory_batches_status", "status"),
    )
