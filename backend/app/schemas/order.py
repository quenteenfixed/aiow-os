"""订单相关的 Pydantic Schema"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class OrderItemRequest(BaseModel):
    """订单商品项"""
    sku_id: str
    qty: int = Field(..., gt=0)
    unit_price: Optional[Decimal] = Field(None, ge=0)


class CustomerInfo(BaseModel):
    """临时客户信息"""
    name: str = Field(..., min_length=1, max_length=64)
    phone: str = Field(..., min_length=4, max_length=32)


class ShippingAddress(BaseModel):
    """收货地址"""
    name: Optional[str] = None
    phone: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    detail: Optional[str] = None


class CreateOrderRequest(BaseModel):
    """创建订单请求"""
    customer_id: Optional[str] = None
    customer_info: Optional[CustomerInfo] = None
    items: List[OrderItemRequest] = Field(..., min_length=1)
    shipping_address: Optional[ShippingAddress] = None
    remark: Optional[str] = Field(None, max_length=512)
    source: Optional[str] = Field("manual", pattern="^(manual|a2a|pos)$")


class CancelOrderRequest(BaseModel):
    """取消订单请求"""
    reason: str = Field(..., min_length=1, max_length=256)


class ShipOrderRequest(BaseModel):
    """发货请求"""
    shipping_company: Optional[str] = Field(None, max_length=64)
    tracking_no: Optional[str] = Field(None, max_length=64)
    remark: Optional[str] = Field(None, max_length=256)


class PayOrderRequest(BaseModel):
    """支付请求"""
    payment_method: str = Field(..., max_length=32, description="支付方式：wechat/alipay/cash/card")


class RefundRequest(BaseModel):
    """退款请求"""
    refund_amount: Decimal = Field(..., ge=0)
    refund_reason: str = Field(..., min_length=1, max_length=256)
    refund_type: str = Field(..., pattern="^(full|partial)$")
