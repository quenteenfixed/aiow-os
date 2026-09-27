"""FastAPI 依赖注入 - 认证、当前用户、权限校验、分页"""
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.response import AuthException, PermissionException
from app.config import settings
from app.core.rbac import Role, has_permission
from app.core.security import decode_token
from app.database import get_db
from app.redis_client import is_token_blacklisted


@dataclass
class CurrentUser:
    """当前用户上下文"""

    user_id: int
    business_id: Optional[int]
    role: str
    token: str
    payload: dict


async def get_current_user(
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """从 Authorization 头解析当前用户"""
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthException("Missing or invalid Authorization header")

    token = authorization[7:]
    payload = decode_token(token)
    if payload is None:
        raise AuthException("Invalid or expired token")

    if payload.get("type") != "access":
        raise AuthException("Invalid token type")

    # 检查黑名单
    if await is_token_blacklisted(token):
        raise AuthException("Token has been revoked")

    user_id = payload.get("user_id")
    if user_id is None:
        raise AuthException("Invalid token payload")

    return CurrentUser(
        user_id=user_id,
        business_id=payload.get("business_id"),
        role=payload.get("role", "user"),
        token=token,
        payload=payload,
    )


async def get_current_user_optional(
    authorization: str = Header(None),
) -> Optional[CurrentUser]:
    """可选的当前用户（允许未登录访问）"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return await get_current_user(authorization)
    except AuthException:
        return None


def require_permission(permission: str):
    """权限校验依赖 - 使用方式：Depends(require_permission("product:read"))"""

    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not has_permission(user.role, permission):
            raise PermissionException(
                f"Permission denied: requires '{permission}'"
            )
        return user

    return _check


def require_role(*roles: str):
    """角色校验依赖 - 使用方式：Depends(require_role("owner", "manager"))"""

    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles and user.role != Role.SUPER_ADMIN.value:
            raise PermissionException(
                f"Role '{user.role}' not allowed. Required: {', '.join(roles)}"
            )
        return user

    return _check


def require_business_access(user: CurrentUser = Depends(get_current_user)) -> int:
    """要求当前用户绑定商户 - 返回 business_id"""
    if user.business_id is None:
        raise PermissionException("No business context")
    return user.business_id


@dataclass
class Pagination:
    """分页参数"""

    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


def get_pagination(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
) -> Pagination:
    """分页参数依赖"""
    return Pagination(page=page, page_size=page_size)
