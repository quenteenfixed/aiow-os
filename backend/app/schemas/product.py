"""商品与 SKU 相关的 Pydantic Schema"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ===== SKU Schema =====
class SKUBase(BaseModel):
    sku_code: str = Field(..., min_length=1, max_length=64, description="SKU 编码")
    spec_name: Optional[str] = Field(None, max_length=128)
    price: Decimal = Field(..., ge=0, description="销售单价")
    cost_price: Optional[Decimal] = Field(None, ge=0)
    original_price: Optional[Decimal] = Field(None, ge=0)
    barcode: Optional[str] = Field(None, max_length=64)
    weight: Optional[Decimal] = Field(None, ge=0)
    image: Optional[str] = Field(None, max_length=512)
    stock_qty: Optional[int] = Field(0, ge=0)
    safety_stock: Optional[int] = Field(0, ge=0)
    min_stock: Optional[int] = Field(0, ge=0)


class SKUCreate(SKUBase):
    pass


class SKUUpdate(BaseModel):
    spec_name: Optional[str] = Field(None, max_length=128)
    price: Optional[Decimal] = Field(None, ge=0)
    cost_price: Optional[Decimal] = Field(None, ge=0)
    original_price: Optional[Decimal] = Field(None, ge=0)
    barcode: Optional[str] = Field(None, max_length=64)
    weight: Optional[Decimal] = Field(None, ge=0)
    image: Optional[str] = Field(None, max_length=512)
    safety_stock: Optional[int] = Field(None, ge=0)
    min_stock: Optional[int] = Field(None, ge=0)
    status: Optional[str] = Field(None, pattern="^(active|inactive)$")


class SKUResponse(BaseModel):
    id: UUID
    product_id: UUID
    sku_code: str
    spec_name: Optional[str] = None
    price: Decimal
    cost_price: Optional[Decimal] = None
    original_price: Optional[Decimal] = None
    barcode: Optional[str] = None
    weight: Optional[Decimal] = None
    image: Optional[str] = None
    stock_qty: int
    safety_stock: int
    min_stock: int
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ===== Product Schema =====
class ProductCreate(BaseModel):
    """创建商品请求"""
    name: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=64)
    brand: Optional[str] = Field(None, max_length=64)
    images: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    base_price: Optional[Decimal] = Field(None, ge=0, description="基准价格（无 SKU 时用于默认 SKU）")
    sort_order: Optional[int] = Field(0, ge=0)
    skus: Optional[List[SKUCreate]] = Field(None, description="SKU 列表，不传则创建默认 SKU")


class ProductUpdate(BaseModel):
    """更新商品请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=256)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=64)
    brand: Optional[str] = Field(None, max_length=64)
    images: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    base_price: Optional[Decimal] = Field(None, ge=0)
    sort_order: Optional[int] = Field(None, ge=0)


class ProductBatchImport(BaseModel):
    """批量导入商品"""
    mode: Optional[str] = Field("create", pattern="^(create|upsert)$")
    products: List[dict] = Field(..., min_length=1)


class UnpublishRequest(BaseModel):
    """下架请求"""
    reason: Optional[str] = Field(None, max_length=256)
