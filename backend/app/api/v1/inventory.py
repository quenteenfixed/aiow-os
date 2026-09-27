"""库存 API 路由"""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_pagination, require_permission
from app.api.response import success_response
from app.database import get_db
from app.schemas.inventory import InventoryAdjustRequest, StocktakeRequest
from app.services.inventory_service import (
    adjust_inventory,
    get_inventory_detail,
    list_batches,
    list_expiring,
    list_inventory,
    list_inventory_alerts,
    list_inventory_logs,
    stocktake,
)

router = APIRouter()


@router.get("", response_model=None)
async def list_inventory_api(
    request: Request,
    keyword: str = Query(None),
    category: str = Query(None),
    sku_code: str = Query(None),
    stock_status: str = Query(None),
    sort_by: str = Query("stock_qty"),
    sort_order: str = Query("asc"),
    pagination: Depends = Depends(get_pagination),
    user: CurrentUser = Depends(require_permission("inventory:read")),
    db: AsyncSession = Depends(get_db),
):
    """库存列表"""
    items, total = await list_inventory(
        db, user.business_id, keyword, category, sku_code,
        stock_status, sort_by, sort_order,
        pagination.page, pagination.page_size,
    )
    total_pages = (total + pagination.page_size - 1) // pagination.page_size if pagination.page_size > 0 else 0
    data = {"items": items, "total": total, "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages}
    return success_response(data, request_id=request.state.request_id)


@router.get("/logs", response_model=None)
async def list_logs_api(
    request: Request,
    sku_id: str = Query(None),
    change_type: str = Query(None),
    operator_type: str = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None),
    pagination: Depends = Depends(get_pagination),
    user: CurrentUser = Depends(require_permission("inventory:read")),
    db: AsyncSession = Depends(get_db),
):
    """库存流水"""
    items, total = await list_inventory_logs(
        db, user.business_id, sku_id, change_type, operator_type,
        start_date, end_date, pagination.page, pagination.page_size,
    )
    total_pages = (total + pagination.page_size - 1) // pagination.page_size if pagination.page_size > 0 else 0
    data = {"items": items, "total": total, "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages}
    return success_response(data, request_id=request.state.request_id)


@router.get("/alerts", response_model=None)
async def list_alerts_api(
    request: Request,
    level: str = Query(None),
    category: str = Query(None),
    pagination: Depends = Depends(get_pagination),
    user: CurrentUser = Depends(require_permission("inventory:read")),
    db: AsyncSession = Depends(get_db),
):
    """库存预警"""
    items, total, summary = await list_inventory_alerts(
        db, user.business_id, level, category, pagination.page, pagination.page_size
    )
    total_pages = (total + pagination.page_size - 1) // pagination.page_size if pagination.page_size > 0 else 0
    data = {"items": items, "total": total, "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages, "summary": summary}
    return success_response(data, request_id=request.state.request_id)


@router.get("/expiring", response_model=None)
async def list_expiring_api(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    category: str = Query(None),
    pagination: Depends = Depends(get_pagination),
    user: CurrentUser = Depends(require_permission("inventory:read")),
    db: AsyncSession = Depends(get_db),
):
    """临期商品"""
    items, total = await list_expiring(
        db, user.business_id, days, category, pagination.page, pagination.page_size
    )
    total_pages = (total + pagination.page_size - 1) // pagination.page_size if pagination.page_size > 0 else 0
    data = {"items": items, "total": total, "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages}
    return success_response(data, request_id=request.state.request_id)


@router.get("/batches", response_model=None)
async def list_batches_api(
    request: Request,
    sku_id: str = Query(None),
    status: str = Query(None),
    expire_before: str = Query(None),
    pagination: Depends = Depends(get_pagination),
    user: CurrentUser = Depends(require_permission("inventory:read")),
    db: AsyncSession = Depends(get_db),
):
    """批次列表"""
    items, total = await list_batches(
        db, user.business_id, sku_id, status, expire_before,
        pagination.page, pagination.page_size,
    )
    total_pages = (total + pagination.page_size - 1) // pagination.page_size if pagination.page_size > 0 else 0
    data = {"items": items, "total": total, "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages}
    return success_response(data, request_id=request.state.request_id)


@router.get("/{sku_id}", response_model=None)
async def get_detail_api(
    sku_id: str,
    request: Request,
    user: CurrentUser = Depends(require_permission("inventory:read")),
    db: AsyncSession = Depends(get_db),
):
    """库存详情"""
    data = await get_inventory_detail(db, user.business_id, sku_id)
    return success_response(data, request_id=request.state.request_id)


@router.post("/adjust", response_model=None)
async def adjust_api(
    req: InventoryAdjustRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("inventory:write")),
    db: AsyncSession = Depends(get_db),
):
    """库存调整（入库/出库/调整）"""
    data = await adjust_inventory(db, user.business_id, user.user_id, req)
    return success_response(data, request_id=request.state.request_id)


@router.post("/stocktake", response_model=None)
async def stocktake_api(
    req: StocktakeRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("inventory:write")),
    db: AsyncSession = Depends(get_db),
):
    """盘点"""
    data = await stocktake(db, user.business_id, user.user_id, req)
    return success_response(data, request_id=request.state.request_id)
