"""认证 API 路由"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.api.response import success_response
from app.config import settings
from app.database import get_db
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RefreshTokenRequest,
    RegisterRequest,
)
from app.services.user_service import (
    get_user_info,
    login as login_service,
    logout as logout_service,
    refresh_token_pair,
    register as register_service,
)

router = APIRouter()


def _user_dict(user):
    """构建用户响应数据（对外用 uuid 作为 id）"""
    return {
        "id": str(user.uuid),
        "email": user.email,
        "phone": user.phone,
        "name": user.name,
        "avatar": user.avatar,
        "status": user.status,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.post("/register", response_model=None)
async def register(
    req: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """用户注册"""
    user, access_token, refresh_token = await register_service(
        db, req.email, req.phone, req.password, req.name
    )
    data = {
        "user": _user_dict(user),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "token_type": "Bearer",
    }
    return success_response(data, request_id=request.state.request_id)


@router.post("/login", response_model=None)
async def login(
    req: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """用户登录"""
    user, access_token, refresh_token, businesses = await login_service(
        db, req.account, req.password
    )
    data = {
        "user": _user_dict(user),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "token_type": "Bearer",
        "businesses": businesses,
    }
    return success_response(data, request_id=request.state.request_id)


@router.post("/logout", response_model=None)
async def logout(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    """用户登出"""
    await logout_service(user.token)
    return success_response(None, request_id=request.state.request_id)


@router.get("/me", response_model=None)
async def me(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户信息"""
    u, businesses = await get_user_info(db, user.user_id)
    data = {
        **_user_dict(u),
        "businesses": businesses,
        "current_business_id": str(businesses[0]["id"]) if businesses else None,
    }
    return success_response(data, request_id=request.state.request_id)


@router.post("/refresh-token", response_model=None)
async def refresh_token(
    req: RefreshTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """刷新 Token"""
    new_access, new_refresh = await refresh_token_pair(db, req.refresh_token)
    data = {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "token_type": "Bearer",
    }
    return success_response(data, request_id=request.state.request_id)
