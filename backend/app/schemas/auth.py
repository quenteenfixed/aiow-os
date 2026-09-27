"""认证相关的 Pydantic Schema"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


# ===== 请求 Schema =====
class RegisterRequest(BaseModel):
    """注册请求"""
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, pattern=r"^1[3-9]\d{9}$")
    password: str = Field(..., min_length=8, max_length=32)
    name: str = Field(..., min_length=2, max_length=32)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """密码需包含字母和数字"""
        has_alpha = any(c.isalpha() for c in v)
        has_digit = any(c.isdigit() for c in v)
        if not (has_alpha and has_digit):
            raise ValueError("密码需包含字母和数字")
        return v

    def has_account(self) -> bool:
        return self.email is not None or self.phone is not None


class LoginRequest(BaseModel):
    """登录请求"""
    account: str = Field(..., description="邮箱或手机号")
    password: str = Field(..., min_length=1)


class RefreshTokenRequest(BaseModel):
    """刷新 Token 请求"""
    refresh_token: str = Field(...)


# ===== 响应 Schema =====
class UserBrief(BaseModel):
    """用户简要信息"""
    id: UUID
    email: Optional[str] = None
    phone: Optional[str] = None
    name: str
    avatar: Optional[str] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BusinessBrief(BaseModel):
    """商户简要信息（登录返回）"""
    id: UUID
    name: str
    slug: str
    role: str

    model_config = {"from_attributes": True}


class BusinessWithCategory(BusinessBrief):
    """带分类的商户信息（me 接口用）"""
    category: str
    status: str


class TokenResponse(BaseModel):
    """Token 响应"""
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"


class RegisterResponse(BaseModel):
    """注册响应"""
    user: UserBrief
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"


class LoginResponse(BaseModel):
    """登录响应"""
    user: UserBrief
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"
    businesses: List[BusinessBrief] = []


class RefreshResponse(BaseModel):
    """刷新响应"""
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"


class MeResponse(BaseModel):
    """当前用户信息"""
    id: UUID
    email: Optional[str] = None
    phone: Optional[str] = None
    name: str
    avatar: Optional[str] = None
    status: str
    created_at: datetime
    businesses: List[BusinessWithCategory] = []
    current_business_id: Optional[UUID] = None
