"""商品与 SKU API 路由"""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    CurrentUser,
    get_current_user,
    get_pagination,
    require_business_access,
    require_permission,
)
from app.api.response import success_response
from app.database import get_db
from app.schemas.product import (
    ProductBatchImport,
    ProductCreate,
    ProductUpdate,
    SKUUpdate,
    UnpublishRequest,
)
from app.services.product_service import (
    batch_import,
    create_product,
    delete_product,
    get_product_detail,
    list_products,
    list_skus,
    publish_product,
    unpublish_product,
    update_product,
    update_sku,
    _product_dict,
    _sku_dict,
)

router = APIRouter()


@router.get("", response_model=None)
async def list_products_api(
    request: Request,
    keyword: str = Query(None),
    category: str = Query(None),
    brand: str = Query(None),
    status: str = Query(None),
    tag: str = Query(None),
    min_price: float = Query(None, ge=0),
    max_price: float = Query(None, ge=0),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    pagination: Depends = Depends(get_pagination),
    user: CurrentUser = Depends(require_permission("product:read")),
    db: AsyncSession = Depends(get_db),
):
    """商品列表"""
    business_id = user.business_id
    items, total = await list_products(
        db, business_id, keyword, category, brand, status, tag,
        min_price, max_price, sort_by, sort_order,
        pagination.page, pagination.page_size,
    )
    total_pages = (total + pagination.page_size - 1) // pagination.page_size if pagination.page_size > 0 else 0
    data = {"items": items, "total": total, "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages}
    return success_response(data, request_id=request.state.request_id)


@router.post("", response_model=None)
async def create_product_api(
    req: ProductCreate,
    request: Request,
    user: CurrentUser = Depends(require_permission("product:write")),
    db: AsyncSession = Depends(get_db),
):
    """创建商品（含 SKU）"""
    product = await create_product(db, user.business_id, req)
    data = await _product_dict(db, product, include_skus=True)
    return success_response(data, request_id=request.state.request_id)


@router.post("/batch-import", response_model=None)
async def batch_import_api(
    req: ProductBatchImport,
    request: Request,
    user: CurrentUser = Depends(require_permission("product:write")),
    db: AsyncSession = Depends(get_db),
):
    """批量导入商品"""
    result = await batch_import(db, user.business_id, req.mode, req.products)
    return success_response(result, request_id=request.state.request_id)


@router.get("/{product_id}/skus", response_model=None)
async def list_skus_api(
    product_id: str,
    request: Request,
    status: str = Query(None),
    user: CurrentUser = Depends(require_permission("product:read")),
    db: AsyncSession = Depends(get_db),
):
    """获取商品 SKU 列表"""
    skus = await list_skus(db, user.business_id, product_id, status)
    return success_response(skus, request_id=request.state.request_id)


@router.get("/{product_id}", response_model=None)
async def get_product_api(
    product_id: str,
    request: Request,
    user: CurrentUser = Depends(require_permission("product:read")),
    db: AsyncSession = Depends(get_db),
):
    """商品详情"""
    product = await get_product_detail(db, user.business_id, product_id)
    data = await _product_dict(db, product, include_skus=True)
    return success_response(data, request_id=request.state.request_id)


@router.put("/{product_id}", response_model=None)
async def update_product_api(
    product_id: str,
    req: ProductUpdate,
    request: Request,
    user: CurrentUser = Depends(require_permission("product:write")),
    db: AsyncSession = Depends(get_db),
):
    """更新商品基础信息"""
    product = await update_product(db, user.business_id, product_id, req)
    data = await _product_dict(db, product, include_skus=True)
    return success_response(data, request_id=request.state.request_id)


@router.delete("/{product_id}", response_model=None)
async def delete_product_api(
    product_id: str,
    request: Request,
    user: CurrentUser = Depends(require_permission("product:delete")),
    db: AsyncSession = Depends(get_db),
):
    """删除商品（软删，archived）"""
    product = await delete_product(db, user.business_id, product_id)
    from datetime import timezone
    data = {
        "id": str(product.uuid),
        "status": product.status,
        "deleted_at": product.deleted_at.isoformat() if product.deleted_at else None,
    }
    return success_response(data, request_id=request.state.request_id)


@router.post("/{product_id}/publish", response_model=None)
async def publish_product_api(
    product_id: str,
    request: Request,
    user: CurrentUser = Depends(require_permission("product:write")),
    db: AsyncSession = Depends(get_db),
):
    """上架商品"""
    product = await publish_product(db, user.business_id, product_id)
    from datetime import timezone
    data = {
        "id": str(product.uuid),
        "status": product.status,
        "published_at": product.updated_at.isoformat() if product.updated_at else None,
    }
    return success_response(data, request_id=request.state.request_id)


@router.post("/{product_id}/unpublish", response_model=None)
async def unpublish_product_api(
    product_id: str,
    request: Request,
    req: UnpublishRequest = None,
    user: CurrentUser = Depends(require_permission("product:write")),
    db: AsyncSession = Depends(get_db),
):
    """下架商品"""
    reason = req.reason if req else None
    product = await unpublish_product(db, user.business_id, product_id, reason)
    data = {
        "id": str(product.uuid),
        "status": product.status,
        "unpublished_at": product.updated_at.isoformat() if product.updated_at else None,
    }
    return success_response(data, request_id=request.state.request_id)


# ===== SKU 独立路由（独立 prefix） =====
sku_router = APIRouter()


@sku_router.put("/{sku_id}", response_model=None)
async def update_sku_api(
    sku_id: str,
    req: SKUUpdate,
    request: Request,
    user: CurrentUser = Depends(require_permission("product:write")),
    db: AsyncSession = Depends(get_db),
):
    """更新 SKU"""
    sku = await update_sku(db, user.business_id, sku_id, req)
    data = _sku_dict(sku)
    return success_response(data, request_id=request.state.request_id)
