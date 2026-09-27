"""库存相关的 Pydantic Schema"""
from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class InventoryAdjustRequest(BaseModel):
    """库存调整请求"""
    sku_id: str = Field(..., description="SKU ID (UUID)")
    change_type: str = Field(..., pattern="^(in|out|adjust)$", description="变动类型")
    change_qty: int = Field(..., description="变动数量（入库为正，出库为负，调整可正可负）")
    reason: str = Field(..., min_length=1, max_length=256, description="变动原因")
    batch_no: Optional[str] = Field(None, max_length=64, description="批次号（入库时可选）")
    expire_date: Optional[date] = Field(None, description="过期日期")
    supplier: Optional[str] = Field(None, max_length=128, description="供应商")


class StocktakeItem(BaseModel):
    """盘点明细项"""
    sku_id: str
    actual_qty: int = Field(..., ge=0)


class StocktakeRequest(BaseModel):
    """盘点请求"""
    items: List[StocktakeItem] = Field(..., min_length=1)
    remark: Optional[str] = Field(None, max_length=256)
