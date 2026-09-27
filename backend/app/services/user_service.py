"""用户服务层 - 认证业务逻辑"""
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.response import AuthException, ConflictException, ValidationException
from app.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import Business, User, UserBusinessRole
from app.redis_client import add_token_to_blacklist


async def register(
    db: AsyncSession,
    email: Optional[str],
    phone: Optional[str],
    password: str,
    name: str,
) -> Tuple[User, str, str]:
    """注册用户 - 返回 (user, access_token, refresh_token)"""
    if not email and not phone:
        raise ValidationException("邮箱或手机号至少填写一个")

    # 检查重复
    conditions = []
    if email:
        conditions.append(User.email == email)
    if phone:
        conditions.append(User.phone == phone)

    stmt = select(User).where(or_(*conditions)).where(User.deleted_at.is_(None))
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise ConflictException("邮箱或手机号已被注册")

    # 创建用户
    user = User(
        email=email,
        phone=phone,
        password_hash=hash_password(password),
        name=name,
        status="active",
    )
    db.add(user)
    await db.flush()

    # 生成 Token
    access_token, _ = create_access_token(user.id)
    refresh_token, _ = create_refresh_token(user.id)

    await db.commit()
    return user, access_token, refresh_token


async def login(
    db: AsyncSession, account: str, password: str
) -> Tuple[User, str, str, List[dict]]:
    """登录 - 返回 (user, access_token, refresh_token, businesses)"""
    # 按邮箱或手机号查找
    stmt = (
        select(User)
        .where(
            or_(User.email == account, User.phone == account),
            User.deleted_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        raise AuthException("账号或密码错误", code=40101)

    if user.status != "active":
        raise AuthException("账号已被禁用", code=40102)

    # 查询用户的商户列表
    biz_stmt = (
        select(Business, UserBusinessRole.role)
        .join(UserBusinessRole, UserBusinessRole.business_id == Business.id)
        .where(
            UserBusinessRole.user_id == user.id,
            UserBusinessRole.status == "active",
            Business.deleted_at.is_(None),
        )
    )
    biz_result = await db.execute(biz_stmt)
    businesses = []
    first_business_id = None
    for biz, role in biz_result:
        if first_business_id is None:
            first_business_id = biz.id
        businesses.append({
            "id": biz.uuid,
            "name": biz.name,
            "slug": biz.slug,
            "role": role,
        })

    # 生成 Token，绑定第一个商户
    access_token, _ = create_access_token(
        user.id, business_id=first_business_id, role=businesses[0]["role"] if businesses else "user"
    )
    refresh_token, _ = create_refresh_token(
        user.id, business_id=first_business_id, role=businesses[0]["role"] if businesses else "user"
    )

    await db.commit()
    return user, access_token, refresh_token, businesses


async def logout(token: str) -> None:
    """登出 - 将 token 加入黑名单"""
    payload = decode_token(token)
    if payload is None:
        raise AuthException("Token 无效", code=40101)

    # 计算剩余有效期，加入黑名单
    exp = payload.get("exp")
    if exp:
        remaining = int(exp) - int(datetime.now(timezone.utc).timestamp())
        if remaining > 0:
            await add_token_to_blacklist(token, remaining)


async def refresh_token_pair(
    db: AsyncSession, refresh_token_str: str
) -> Tuple[str, str]:
    """刷新 Token - 返回 (new_access, new_refresh)"""
    payload = decode_token(refresh_token_str)
    if payload is None:
        raise AuthException("refresh_token 无效或已过期", code=40103)

    if payload.get("type") != "refresh":
        raise AuthException("Token 类型错误", code=40103)

    user_id = payload.get("user_id")
    business_id = payload.get("business_id")
    role = payload.get("role", "user")

    # 检查黑名单
    from app.redis_client import is_token_blacklisted
    if await is_token_blacklisted(refresh_token_str):
        raise AuthException("refresh_token 已失效", code=40103)

    # 生成新 Token
    new_access, _ = create_access_token(user_id, business_id, role)
    new_refresh, _ = create_refresh_token(user_id, business_id, role)

    # 旧 refresh 加入黑名单
    exp = payload.get("exp")
    if exp:
        remaining = int(exp) - int(datetime.now(timezone.utc).timestamp())
        if remaining > 0:
            await add_token_to_blacklist(refresh_token_str, remaining)

    return new_access, new_refresh


async def get_user_info(
    db: AsyncSession, user_id: int
) -> Tuple[User, List[dict]]:
    """获取用户信息 + 商户列表"""
    stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthException("用户不存在", code=40101)

    biz_stmt = (
        select(Business, UserBusinessRole.role)
        .join(UserBusinessRole, UserBusinessRole.business_id == Business.id)
        .where(
            UserBusinessRole.user_id == user_id,
            UserBusinessRole.status == "active",
            Business.deleted_at.is_(None),
        )
    )
    biz_result = await db.execute(biz_stmt)
    businesses = []
    for biz, role in biz_result:
        businesses.append({
            "id": biz.uuid,
            "name": biz.name,
            "slug": biz.slug,
            "category": biz.category,
            "status": biz.status,
            "role": role,
        })

    return user, businesses
