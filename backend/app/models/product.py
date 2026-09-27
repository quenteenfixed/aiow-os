"""商品与 SKU 模型"""
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import BigInteger, ForeignKey, Index, String, Integer, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, SoftDeleteMixin, UUIDMixin
from app.database import Base


class Product(Base, TimestampMixin, SoftDeleteMixin, UUIDMixin):
    """商品 SPU"""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    brand: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    images: Mapped[Optional[list]] = mapped_column(ARRAY(String), server_default=text("'{}'"))
    tags: Mapped[Optional[list]] = mapped_column(ARRAY(String), server_default=text("'{}'"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 关系
    business: Mapped["Business"] = relationship(back_populates="products")
    skus: Mapped[List["SKU"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_products_business_id_status", "business_id", "status"),
        Index("idx_products_business_id_category", "business_id", "category"),
        Index("idx_products_deleted_at", "deleted_at"),
    )


class SKU(Base, TimestampMixin, SoftDeleteMixin, UUIDMixin):
    """库存单元 SKU"""

    __tablename__ = "skus"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False
    )
    business_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("businesses.id"), nullable=False
    )
    sku_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    spec_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    price: Mapped[Decimal] = mapped_column(nullable=False, default=Decimal("0.00"))
    cost_price: Mapped[Optional[Decimal]] = mapped_column(default=Decimal("0.00"))
    original_price: Mapped[Optional[Decimal]] = mapped_column(default=Decimal("0.00"))
    barcode: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    weight: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    image: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    stock_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    safety_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    min_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    # 关系
    product: Mapped["Product"] = relationship(back_populates="skus")
    business: Mapped["Business"] = relationship(back_populates="skus")
    inventory_logs: Mapped[List["InventoryLog"]] = relationship(back_populates="sku")
    inventory_batches: Mapped[List["InventoryBatch"]] = relationship(back_populates="sku")

    __table_args__ = (
        Index("idx_skus_product_id", "product_id"),
        Index("idx_skus_business_id_status", "business_id", "status"),
        Index("idx_skus_barcode", "barcode"),
        Index("idx_skus_stock_qty", "stock_qty"),
        Index("idx_skus_deleted_at", "deleted_at"),
    )
