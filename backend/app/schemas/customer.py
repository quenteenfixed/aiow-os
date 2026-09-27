"""客户档案 Schema"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class CustomerCreateRequest(BaseModel):
    """创建客户档案"""
    name: str = Field(..., min_length=1, max_length=64)
    phone: Optional[str] = Field(None, max_length=32)
    email: Optional[str] = Field(None, max_length=128)
    avatar: Optional[str] = Field(None, max_length=512)
    level: Optional[str] = Field("normal", pattern="^(normal|vip|svip)$")
    tags: Optional[List[str]] = None


class CustomerUpdateRequest(BaseModel):
    """更新客户档案"""
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    phone: Optional[str] = Field(None, max_length=32)
    email: Optional[str] = Field(None, max_length=128)
    avatar: Optional[str] = Field(None, max_length=512)


class CustomerLevelRequest(BaseModel):
    """手动调整客户等级"""
    level: str = Field(..., pattern="^(normal|vip|svip)$")


class CustomerTagsRequest(BaseModel):
    """批量替换客户标签"""
    tags: List[str] = Field(..., min_length=0, max_length=20)


class CustomerTagAddRequest(BaseModel):
    """新增单个标签"""
    tag: str = Field(..., min_length=1, max_length=32)
