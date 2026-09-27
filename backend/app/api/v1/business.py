"""商业实体 API 路由"""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import CurrentUser, get_current_user, get_pagination
from app.api.response import success_response
from app.database import get_db
from app.models import Agent, User
from app.schemas.business import (
    CreateBusinessRequest,
    UpdateBusinessConfigRequest,
    UpdateBusinessRequest,
)
from app.services.business_service import (
    create_business,
    get_business_detail,
    get_business_stats,
    list_my_businesses,
    update_business,
    update_business_config,
)

router = APIRouter()


@router.post("", response_model=None)
async def create_biz(
    req: CreateBusinessRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建商业实体（创建者自动成为 owner）"""
    biz = await create_business(db, user.user_id, req)
    data = {
        "id": str(biz.uuid),
        "name": biz.name,
        "slug": biz.slug,
        "category": biz.category,
        "sub_category": biz.sub_category,
        "business_model": biz.business_model,
        "address": biz.address,
        "city": biz.city,
        "province": biz.province,
        "country": biz.country,
        "timezone": biz.timezone,
        "currency": biz.currency,
        "status": biz.status,
        "owner_id": str(user.uuid) if hasattr(user, "uuid") and user.uuid else None,
        "agent_id": None,
        "config": biz.config or {},
        "created_at": biz.created_at.isoformat() if biz.created_at else None,
        "updated_at": biz.updated_at.isoformat() if biz.updated_at else None,
    }
    # owner_id 用当前用户 uuid（创建者即 owner）
    owner = await db.execute(select(User.uuid).where(User.id == biz.owner_id))
    owner_uuid = owner.scalar_one_or_none()
    if owner_uuid is not None:
        data["owner_id"] = str(owner_uuid)
    return success_response(data, request_id=request.state.request_id)


@router.get("", response_model=None)
async def list_biz(
    request: Request,
    status: str = Query(None, description="按状态筛选"),
    pagination: Depends = Depends(get_pagination),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取我的商业实体列表"""
    items, total = await list_my_businesses(
        db, user.user_id, status, pagination.page, pagination.page_size
    )
    total_pages = (total + pagination.page_size - 1) // pagination.page_size if pagination.page_size > 0 else 0
    data = {
        "items": items,
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
        "total_pages": total_pages,
    }
    return success_response(data, request_id=request.state.request_id)


@router.get("/{biz_id}", response_model=None)
async def get_biz(
    biz_id: str,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取商业实体详情"""
    biz, role, agent = await get_business_detail(db, user.user_id, biz_id)

    # 查 owner 的 uuid
    owner_uuid = None
    if biz.owner_id is not None:
        result = await db.execute(select(User.uuid).where(User.id == biz.owner_id))
        owner_uuid = result.scalar_one_or_none()

    # agent uuid
    agent_uuid = None
    if agent is not None:
        agent_uuid = str(agent.uuid)

    data = {
        "id": str(biz.uuid),
        "name": biz.name,
        "slug": biz.slug,
        "category": biz.category,
        "sub_category": biz.sub_category,
        "business_model": biz.business_model,
        "address": biz.address,
        "city": biz.city,
        "province": biz.province,
        "country": biz.country,
        "timezone": biz.timezone,
        "currency": biz.currency,
        "status": biz.status,
        "owner_id": str(owner_uuid) if owner_uuid else None,
        "agent_id": str(agent_uuid) if agent_uuid else None,
        "config": biz.config or {},
        "created_at": biz.created_at.isoformat() if biz.created_at else None,
        "updated_at": biz.updated_at.isoformat() if biz.updated_at else None,
    }
    return success_response(data, request_id=request.state.request_id)


@router.put("/{biz_id}", response_model=None)
async def update_biz(
    biz_id: str,
    req: UpdateBusinessRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新商业实体基础信息（需 owner/manager）"""
    biz = await update_business(db, user.user_id, biz_id, req)
    # 查 owner uuid
    owner_uuid = None
    if biz.owner_id is not None:
        result = await db.execute(select(User.uuid).where(User.id == biz.owner_id))
        owner_uuid = result.scalar_one_or_none()
    data = {
        "id": str(biz.uuid),
        "name": biz.name,
        "slug": biz.slug,
        "category": biz.category,
        "sub_category": biz.sub_category,
        "business_model": biz.business_model,
        "address": biz.address,
        "city": biz.city,
        "province": biz.province,
        "country": biz.country,
        "timezone": biz.timezone,
        "currency": biz.currency,
        "status": biz.status,
        "owner_id": str(owner_uuid) if owner_uuid else None,
        "agent_id": None,
        "config": biz.config or {},
        "created_at": biz.created_at.isoformat() if biz.created_at else None,
        "updated_at": biz.updated_at.isoformat() if biz.updated_at else None,
    }
    return success_response(data, request_id=request.state.request_id)


@router.post("/{biz_id}/config", response_model=None)
async def update_biz_config(
    biz_id: str,
    req: UpdateBusinessConfigRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新商业实体经营参数（需 owner/manager）"""
    config = await update_business_config(db, user.user_id, biz_id, req)
    return success_response(config, request_id=request.state.request_id)


@router.get("/{biz_id}/stats", response_model=None)
async def get_biz_stats(
    biz_id: str,
    request: Request,
    period: str = Query("today", description="统计周期：today / 7d / 30d"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取商业实体经营统计概览"""
    stats = await get_business_stats(db, user.user_id, biz_id, period)
    return success_response(stats, request_id=request.state.request_id)
