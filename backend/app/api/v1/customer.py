"""客户档案 API - M1-6"""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    CurrentUser,
    get_db,
    get_pagination,
    require_permission,
)
from app.api.response import success_response
from app.schemas.customer import (
    CustomerCreateRequest,
    CustomerLevelRequest,
    CustomerTagAddRequest,
    CustomerTagsRequest,
    CustomerUpdateRequest,
)
from app.services import customer_service

router = APIRouter()


@router.get("/stats", response_model=None)
async def get_customer_stats(
    request: Request,
    user: CurrentUser = Depends(require_permission("customer:read")),
    db: AsyncSession = Depends(get_db),
):
    """客户统计：等级分布、累计消费"""
    data = await customer_service.get_customer_stats(db, user.business_id)
    return success_response(data, request_id=request.state.request_id)


@router.get("", response_model=None)
async def list_customers(
    request: Request,
    keyword: str | None = Query(None, description="关键字（name/phone/email）"),
    level: str | None = Query(None, pattern="^(normal|vip|svip)$"),
    tag: str | None = Query(None, description="标签过滤"),
    sort_by: str = Query("created_at", pattern="^(created_at|total_amount|total_orders|last_order_at)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    pagination: Depends = Depends(get_pagination),
    user: CurrentUser = Depends(require_permission("customer:read")),
    db: AsyncSession = Depends(get_db),
):
    """客户列表（关键字/等级/标签过滤 + 分页）"""
    items, total = await customer_service.list_customers(
        db, user.business_id, keyword, level, tag,
        sort_by, sort_order, pagination.page, pagination.page_size,
    )
    total_pages = (total + pagination.page_size - 1) // pagination.page_size if pagination.page_size > 0 else 0
    return success_response({
        "items": items,
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
        "total_pages": total_pages,
    }, request_id=request.state.request_id)


@router.post("", response_model=None)
async def create_customer(
    body: CustomerCreateRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("customer:write")),
    db: AsyncSession = Depends(get_db),
):
    """创建客户档案"""
    customer = await customer_service.create_customer(db, user.business_id, body)
    return success_response(
        customer_service._customer_dict(customer),
        request_id=request.state.request_id,
    )


@router.get("/{customer_uuid}", response_model=None)
async def get_customer_detail(
    customer_uuid: str,
    request: Request,
    user: CurrentUser = Depends(require_permission("customer:read")),
    db: AsyncSession = Depends(get_db),
):
    """客户详情（含最近 50 单订单历史）"""
    customer, orders = await customer_service.get_customer_detail(
        db, user.business_id, customer_uuid
    )
    return success_response(
        customer_service._customer_dict(customer, include_orders=True, orders_data=orders),
        request_id=request.state.request_id,
    )


@router.put("/{customer_uuid}", response_model=None)
async def update_customer(
    body: CustomerUpdateRequest,
    customer_uuid: str,
    request: Request,
    user: CurrentUser = Depends(require_permission("customer:write")),
    db: AsyncSession = Depends(get_db),
):
    """更新客户档案"""
    customer = await customer_service.update_customer(
        db, user.business_id, customer_uuid, body
    )
    return success_response(
        customer_service._customer_dict(customer),
        request_id=request.state.request_id,
    )


@router.delete("/{customer_uuid}", response_model=None)
async def delete_customer(
    customer_uuid: str,
    request: Request,
    user: CurrentUser = Depends(require_permission("customer:delete")),
    db: AsyncSession = Depends(get_db),
):
    """软删除客户档案"""
    customer = await customer_service.delete_customer(
        db, user.business_id, customer_uuid
    )
    return success_response(
        customer_service._customer_dict(customer),
        request_id=request.state.request_id,
    )


# ===== 标签管理 =====
@router.put("/{customer_uuid}/tags", response_model=None)
async def replace_tags(
    body: CustomerTagsRequest,
    customer_uuid: str,
    request: Request,
    user: CurrentUser = Depends(require_permission("customer:write")),
    db: AsyncSession = Depends(get_db),
):
    """批量替换客户标签"""
    customer = await customer_service.replace_tags(
        db, user.business_id, customer_uuid, body.tags
    )
    return success_response(
        customer_service._customer_dict(customer),
        request_id=request.state.request_id,
    )


@router.post("/{customer_uuid}/tags", response_model=None)
async def add_tag(
    body: CustomerTagAddRequest,
    customer_uuid: str,
    request: Request,
    user: CurrentUser = Depends(require_permission("customer:write")),
    db: AsyncSession = Depends(get_db),
):
    """新增单个标签"""
    customer = await customer_service.add_tag(
        db, user.business_id, customer_uuid, body.tag
    )
    return success_response(
        customer_service._customer_dict(customer),
        request_id=request.state.request_id,
    )


@router.delete("/{customer_uuid}/tags/{tag}", response_model=None)
async def remove_tag(
    customer_uuid: str,
    tag: str,
    request: Request,
    user: CurrentUser = Depends(require_permission("customer:write")),
    db: AsyncSession = Depends(get_db),
):
    """移除单个标签"""
    customer = await customer_service.remove_tag(
        db, user.business_id, customer_uuid, tag
    )
    return success_response(
        customer_service._customer_dict(customer),
        request_id=request.state.request_id,
    )


# ===== 等级管理 =====
@router.put("/{customer_uuid}/level", response_model=None)
async def set_level(
    body: CustomerLevelRequest,
    customer_uuid: str,
    request: Request,
    user: CurrentUser = Depends(require_permission("customer:write")),
    db: AsyncSession = Depends(get_db),
):
    """手动调整客户等级"""
    customer = await customer_service.set_level(
        db, user.business_id, customer_uuid, body.level
    )
    return success_response(
        customer_service._customer_dict(customer),
        request_id=request.state.request_id,
    )


@router.post("/recalc-levels", response_model=None)
async def recalc_levels(
    request: Request,
    user: CurrentUser = Depends(require_permission("customer:write")),
    db: AsyncSession = Depends(get_db),
):
    """批量重算所有客户等级（基于累计消费金额）"""
    data = await customer_service.recalc_levels(db, user.business_id)
    return success_response(data, request_id=request.state.request_id)
