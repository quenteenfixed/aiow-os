"""商业实体相关的 Pydantic Schema"""
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ===== 请求 Schema =====
class CreateBusinessRequest(BaseModel):
    """创建商业实体请求"""
    name: str = Field(..., min_length=2, max_length=128, description="商业名称")
    slug: str = Field(..., min_length=3, max_length=64, description="URL 友好标识，全局唯一")
    category: str = Field(..., description="行业大类：retail / restaurant / service / ecommerce")
    sub_category: Optional[str] = Field(None, max_length=32, description="行业子类")
    business_model: Optional[str] = Field(None, description="经营模式：b2c / b2b / d2c")
    address: Optional[str] = Field(None, max_length=256, description="详细地址")
    city: Optional[str] = Field(None, max_length=64, description="城市")
    province: Optional[str] = Field(None, max_length=64, description="省份")
    country: Optional[str] = Field("CN", max_length=64, description="国家")
    timezone: Optional[str] = Field("Asia/Shanghai", max_length=64, description="时区")
    currency: Optional[str] = Field("CNY", max_length=16, description="货币代码")
    template: Optional[str] = Field(None, description="行业模板标识")

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """slug 仅允许小写字母、数字和连字符"""
        if not v:
            raise ValueError("slug 不能为空")
        for c in v:
            if not (c.islower() or c.isdigit() or c == "-"):
                raise ValueError("slug 仅允许小写字母、数字和连字符")
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("slug 不能以连字符开头或结尾")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        allowed = {"retail", "restaurant", "service", "ecommerce"}
        if v not in allowed:
            raise ValueError(f"category 必须是 {allowed} 之一")
        return v

    @field_validator("business_model")
    @classmethod
    def validate_business_model(cls, v):
        if v is None:
            return v
        allowed = {"b2c", "b2b", "d2c"}
        if v not in allowed:
            raise ValueError(f"business_model 必须是 {allowed} 之一")
        return v


class UpdateBusinessRequest(BaseModel):
    """更新商业实体基础信息请求"""
    name: Optional[str] = Field(None, min_length=2, max_length=128)
    category: Optional[str] = Field(None)
    sub_category: Optional[str] = Field(None, max_length=32)
    business_model: Optional[str] = Field(None)
    address: Optional[str] = Field(None, max_length=256)
    city: Optional[str] = Field(None, max_length=64)
    province: Optional[str] = Field(None, max_length=64)
    country: Optional[str] = Field(None, max_length=64)
    timezone: Optional[str] = Field(None, max_length=64)
    currency: Optional[str] = Field(None, max_length=16)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        if v is None:
            return v
        allowed = {"retail", "restaurant", "service", "ecommerce"}
        if v not in allowed:
            raise ValueError(f"category 必须是 {allowed} 之一")
        return v

    @field_validator("business_model")
    @classmethod
    def validate_business_model(cls, v):
        if v is None:
            return v
        allowed = {"b2c", "b2b", "d2c"}
        if v not in allowed:
            raise ValueError(f"business_model 必须是 {allowed} 之一")
        return v


class UpdateBusinessConfigRequest(BaseModel):
    """更新商业实体经营参数请求"""
    business_hours: Optional[str] = Field(None, description="营业时间描述")
    min_profit_rate: Optional[float] = Field(None, ge=0, le=1, description="最低利润率")
    inventory_alert_threshold: Optional[int] = Field(None, ge=0, description="库存预警默认阈值")
    price_adjust_approval_threshold: Optional[float] = Field(
        None, ge=0, le=1, description="价格调整审批阈值"
    )
    daily_loss_limit: Optional[float] = Field(None, ge=0, description="单日亏损上限")
    auto_approve_low_risk: Optional[bool] = Field(None, description="是否自动审批低风险工单")
    notify_config: Optional[dict] = Field(None, description="通知配置")


class BusinessListQuery(BaseModel):
    """商业实体列表查询参数"""
    status: Optional[str] = None
    page: int = 1
    page_size: int = 20


class BusinessStatsQuery(BaseModel):
    """商业实体统计查询参数"""
    period: str = "today"  # today / 7d / 30d
