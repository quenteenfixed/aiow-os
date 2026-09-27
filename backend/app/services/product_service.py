"""商品与 SKU 服务层"""
from decimal import Decimal
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.response import (
    ConflictException,
    NotFoundException,
    PermissionException,
    ValidationException,
)
from app.models import Order, OrderItem, Product, SKU


# ===== 辅助函数 =====
async def _get_product_by_uuid(
    db: AsyncSession, business_id: int, product_uuid: str, for_update: bool = False
) -> Product:
    """按 UUID 查询商品（含商户隔离 + 软删除过滤）"""
    try:
        uid = UUID(product_uuid)
    except (ValueError, AttributeError):
        raise ValidationException("商品 ID 格式错误")

    stmt = select(Product).where(
        Product.uuid == uid,
        Product.business_id == business_id,
        Product.deleted_at.is_(None),
    )
    if for_update:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    product = result.scalar_one_or_none()
    if product is None:
        raise NotFoundException("商品不存在")
    return product


async def _get_sku_by_uuid(
    db: AsyncSession, business_id: int, sku_uuid: str, for_update: bool = False
) -> SKU:
    """按 UUID 查询 SKU"""
    try:
        uid = UUID(sku_uuid)
    except (ValueError, AttributeError):
        raise ValidationException("SKU ID 格式错误")

    stmt = select(SKU).where(
        SKU.uuid == uid,
        SKU.business_id == business_id,
        SKU.deleted_at.is_(None),
    )
    if for_update:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    sku = result.scalar_one_or_none()
    if sku is None:
        raise NotFoundException("SKU 不存在")
    return sku


def _sku_dict(sku: SKU) -> dict:
    return {
        "id": str(sku.uuid),
        "product_id": str(sku.product_id) if sku.product_id else None,
        "sku_code": sku.sku_code,
        "spec_name": sku.spec_name,
        "price": float(sku.price) if sku.price is not None else None,
        "cost_price": float(sku.cost_price) if sku.cost_price is not None else None,
        "original_price": float(sku.original_price) if sku.original_price is not None else None,
        "barcode": sku.barcode,
        "weight": float(sku.weight) if sku.weight is not None else None,
        "image": sku.image,
        "stock_qty": sku.stock_qty,
        "safety_stock": sku.safety_stock,
        "min_stock": sku.min_stock,
        "status": sku.status,
        "created_at": sku.created_at.isoformat() if sku.created_at else None,
        "updated_at": sku.updated_at.isoformat() if sku.updated_at else None,
    }


async def _product_dict(db: AsyncSession, product: Product, include_skus: bool = False) -> dict:
    """构建商品响应数据（含 base_price/sku_count/total_stock 聚合）"""
    # 聚合 SKU 数据
    agg_stmt = select(
        func.count(SKU.id),
        func.coalesce(func.sum(SKU.stock_qty), 0),
        func.min(SKU.price),
    ).where(
        SKU.product_id == product.id,
        SKU.business_id == product.business_id,
        SKU.deleted_at.is_(None),
    )
    agg_result = await db.execute(agg_stmt)
    sku_count, total_stock, min_price = agg_result.one()

    data = {
        "id": str(product.uuid),
        "name": product.name,
        "description": product.description,
        "category": product.category,
        "brand": product.brand,
        "images": product.images or [],
        "tags": product.tags or [],
        "status": product.status,
        "base_price": float(min_price) if min_price is not None else None,
        "sort_order": product.sort_order,
        "sku_count": sku_count,
        "total_stock": total_stock,
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "updated_at": product.updated_at.isoformat() if product.updated_at else None,
    }
    if include_skus:
        skus_stmt = select(SKU).where(
            SKU.product_id == product.id,
            SKU.deleted_at.is_(None),
        ).order_by(SKU.id)
        skus_result = await db.execute(skus_stmt)
        data["skus"] = [_sku_dict(s) for s in skus_result.scalars()]
    return data


# ===== 商品 CRUD =====
async def list_products(
    db: AsyncSession,
    business_id: int,
    keyword: Optional[str],
    category: Optional[str],
    brand: Optional[str],
    status: Optional[str],
    tag: Optional[str],
    min_price: Optional[float],
    max_price: Optional[float],
    sort_by: str,
    sort_order: str,
    page: int,
    page_size: int,
) -> Tuple[list, int]:
    """商品列表"""
    stmt = select(Product).where(
        Product.business_id == business_id,
        Product.deleted_at.is_(None),
    )
    if keyword:
        stmt = stmt.where(Product.name.ilike(f"%{keyword}%"))
    if category:
        stmt = stmt.where(Product.category == category)
    if brand:
        stmt = stmt.where(Product.brand == brand)
    if status:
        stmt = stmt.where(Product.status == status)
    if tag:
        stmt = stmt.where(Product.tags.any(tag))

    # 价格筛选需关联 SKU
    if min_price is not None or max_price is not None:
        stmt = stmt.join(SKU, SKU.product_id == Product.id)
        if min_price is not None:
            stmt = stmt.where(SKU.price >= min_price)
        if max_price is not None:
            stmt = stmt.where(SKU.price <= max_price)
        stmt = stmt.distinct()

    # 排序
    sort_map = {
        "name": Product.name,
        "created_at": Product.created_at,
        "sort_order": Product.sort_order,
    }
    sort_col = sort_map.get(sort_by, Product.created_at)
    if sort_order == "asc":
        stmt = stmt.order_by(sort_col.asc())
    else:
        stmt = stmt.order_by(sort_col.desc())

    # 总数
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # 分页
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    products = result.scalars().unique()

    items = [await _product_dict(db, p, include_skus=False) for p in products]
    return items, total


async def create_product(
    db: AsyncSession, business_id: int, req
) -> Product:
    """创建商品 + 关联 SKU"""
    # 校验 SKU 编码唯一
    sku_codes = [s.sku_code for s in (req.skus or [])]
    if sku_codes:
        if len(set(sku_codes)) != len(sku_codes):
            raise ValidationException("SKU 编码在请求内重复")
        existing = await db.execute(
            select(SKU.id).where(SKU.sku_code.in_(sku_codes))
        )
        if existing.first() is not None:
            raise ConflictException("SKU 编码已存在")

    # 确定默认 SKU 价格
    skus_data = req.skus or []
    if not skus_data:
        # 创建默认 SKU
        default_price = req.base_price if req.base_price is not None else Decimal("0")
        skus_data = [{
            "sku_code": f"DEFAULT-{__import__('uuid').uuid4().hex[:12].upper()}",
            "spec_name": "默认规格",
            "price": default_price,
        }]

    product = Product(
        business_id=business_id,
        name=req.name,
        description=req.description,
        category=req.category,
        brand=req.brand,
        images=req.images or [],
        tags=req.tags or [],
        status="draft",
        sort_order=req.sort_order or 0,
    )
    db.add(product)
    await db.flush()

    for sku_data in skus_data:
        # 兼容 Pydantic 模型与 dict（默认 SKU 走 dict 路径）
        if isinstance(sku_data, dict):
            g = lambda k: sku_data.get(k)
        else:
            g = lambda k: getattr(sku_data, k, None)
        sku = SKU(
            product_id=product.id,
            business_id=business_id,
            sku_code=g("sku_code"),
            spec_name=g("spec_name"),
            price=g("price"),
            cost_price=g("cost_price"),
            original_price=g("original_price"),
            barcode=g("barcode"),
            weight=g("weight"),
            image=g("image"),
            stock_qty=g("stock_qty") or 0,
            safety_stock=g("safety_stock") or 0,
            min_stock=g("min_stock") or 0,
            status="active",
        )
        db.add(sku)

    await db.commit()
    await db.refresh(product)
    return product


async def get_product_detail(
    db: AsyncSession, business_id: int, product_uuid: str
) -> Product:
    """获取商品详情（含 SKU 列表）"""
    return await _get_product_by_uuid(db, business_id, product_uuid)


async def update_product(
    db: AsyncSession, business_id: int, product_uuid: str, req
) -> Product:
    """更新商品基础信息"""
    product = await _get_product_by_uuid(db, business_id, product_uuid, for_update=True)
    if product.status == "archived":
        raise ConflictException("已归档商品无法修改")

    update_fields = ["name", "description", "category", "brand", "images", "tags", "sort_order"]
    changed = False
    for field in update_fields:
        val = getattr(req, field, None)
        if val is not None:
            setattr(product, field, val)
            changed = True
    if not changed:
        raise ValidationException("至少需要提供一个更新字段")

    await db.commit()
    await db.refresh(product)
    return product


async def delete_product(
    db: AsyncSession, business_id: int, product_uuid: str
) -> Product:
    """软删除商品（archived）"""
    product = await _get_product_by_uuid(db, business_id, product_uuid, for_update=True)
    if product.status == "archived":
        raise ConflictException("商品已归档")

    # 检查有无未完成订单（占用该商品的 SKU）—— OrderItem 通过 sku_id 关联
    sku_ids_stmt = select(SKU.id).where(
        SKU.product_id == product.id, SKU.deleted_at.is_(None)
    )
    pending_check = await db.execute(
        select(func.count()).select_from(OrderItem).join(
            Order, Order.id == OrderItem.order_id
        ).where(
            OrderItem.sku_id.in_(sku_ids_stmt),
            Order.business_id == business_id,
            Order.status.in_(["pending", "paid", "shipped"]),
            Order.deleted_at.is_(None),
        )
    )
    pending_count = pending_check.scalar_one()
    if pending_count > 0:
        raise ConflictException("商品存在未完成订单，无法删除")

    from datetime import datetime, timezone
    product.status = "archived"
    product.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    await db.refresh(product)
    return product


async def publish_product(
    db: AsyncSession, business_id: int, product_uuid: str
) -> Product:
    """上架商品：draft/inactive → active"""
    product = await _get_product_by_uuid(db, business_id, product_uuid, for_update=True)
    if product.status == "archived":
        raise ConflictException("已归档商品无法上架")
    if product.status == "active":
        raise ConflictException("商品已上架")
    product.status = "active"
    await db.commit()
    await db.refresh(product)
    return product


async def unpublish_product(
    db: AsyncSession, business_id: int, product_uuid: str, reason: Optional[str]
) -> Product:
    """下架商品：active → inactive"""
    product = await _get_product_by_uuid(db, business_id, product_uuid, for_update=True)
    if product.status != "active":
        raise ConflictException("仅 active 状态商品可下架")
    product.status = "inactive"
    await db.commit()
    await db.refresh(product)
    return product


# ===== SKU =====
async def list_skus(
    db: AsyncSession, business_id: int, product_uuid: str, status: Optional[str]
) -> list:
    """获取商品的 SKU 列表"""
    product = await _get_product_by_uuid(db, business_id, product_uuid)
    stmt = select(SKU).where(
        SKU.product_id == product.id,
        SKU.deleted_at.is_(None),
    )
    if status:
        stmt = stmt.where(SKU.status == status)
    stmt = stmt.order_by(SKU.id)
    result = await db.execute(stmt)
    return [_sku_dict(s) for s in result.scalars()]


async def update_sku(
    db: AsyncSession, business_id: int, sku_uuid: str, req
) -> SKU:
    """更新 SKU"""
    sku = await _get_sku_by_uuid(db, business_id, sku_uuid, for_update=True)
    update_fields = [
        "spec_name", "price", "cost_price", "original_price",
        "barcode", "weight", "image", "safety_stock", "min_stock", "status",
    ]
    changed = False
    for field in update_fields:
        val = getattr(req, field, None)
        if val is not None:
            setattr(sku, field, val)
            changed = True
    if not changed:
        raise ValidationException("至少需要提供一个更新字段")
    await db.commit()
    await db.refresh(sku)
    return sku


# ===== 批量导入 =====
async def batch_import(
    db: AsyncSession, business_id: int, mode: str, products_data: List[dict]
) -> dict:
    """批量导入商品（简化实现：循环创建，失败记录）"""
    from app.schemas.product import ProductCreate
    success_count = 0
    failed_items = []
    for idx, item in enumerate(products_data):
        try:
            # 补全必填字段
            if "base_price" not in item and "skus" not in item:
                raise ValidationException("缺少 base_price 或 skus")
            req = ProductCreate(**item)
            await create_product(db, business_id, req)
            success_count += 1
        except ConflictException as e:
            if mode == "upsert":
                # upsert 模式：尝试按 sku_code 更新（简化：跳过）
                failed_items.append({"row": idx + 1, "sku_code": item.get("sku_code"), "error": str(e)})
            else:
                failed_items.append({"row": idx + 1, "sku_code": item.get("sku_code"), "error": str(e)})
        except Exception as e:
            failed_items.append({"row": idx + 1, "sku_code": item.get("sku_code"), "error": str(e)})
    return {
        "total": len(products_data),
        "success_count": success_count,
        "failed_count": len(failed_items),
        "failed_items": failed_items,
    }
