"""A2A 网关 API - 外部 Agent 接入

认证方式：X-A2A-API-Key 请求头（与内部 JWT 完全隔离）
所有响应通过 Fencing 包装，防止提示注入扩散。
"""
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.response import success_response
from app.database import get_db
from app.services.a2a_service import (
    register_agent, authenticate_api_key, check_rate_limit,
    log_gateway_request, get_capabilities, fence_response,
    search_products, get_product_detail_a2a, search_inventory,
    create_order_a2a, get_order_a2a, get_business_for_agent,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ===== 依赖：API Key 认证 =====

async def get_a2a_agent(
    x_a2a_api_key: Optional[str] = Header(None, alias="X-A2A-API-Key"),
    db: AsyncSession = Depends(get_db),
):
    """从 X-A2A-API-Key 头认证外部 Agent"""
    agent, err = await authenticate_api_key(db, x_a2a_api_key or "")
    if err:
        raise HTTPException(status_code=401, detail=err)
    # 限流检查
    if not check_rate_limit(agent):
        raise HTTPException(status_code=429, detail="请求频率超限，请稍后重试")
    return agent


# ===== 请求/响应模型 =====

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    developer: Optional[str] = Field(None, max_length=128)
    business_id: Optional[int] = None
    rate_limit_per_min: int = Field(60, ge=1, le=1000)


class A2AOrderItem(BaseModel):
    sku_id: str
    qty: int = Field(..., ge=1)
    unit_price: Optional[float] = None


class A2ACustomerInfo(BaseModel):
    name: str
    phone: Optional[str] = None


class A2ACreateOrderRequest(BaseModel):
    items: list[A2AOrderItem]
    customer_id: Optional[int] = None
    customer_info: Optional[A2ACustomerInfo] = None
    remark: Optional[str] = None


# ===== 网关日志中间件装饰（在每个接口内手动调用）=====

async def _log_and_fence(
    request: Request,
    db: AsyncSession,
    agent,
    business_id: int,
    start: float,
    data,
    status_code: int = 200,
    error: Optional[str] = None,
):
    """记录网关日志并返回 Fencing 包装后的响应"""
    elapsed_ms = int((time.time() - start) * 1000)
    try:
        await log_gateway_request(
            db, agent, business_id,
            endpoint=request.url.path,
            method=request.method,
            status_code=status_code,
            response_time_ms=elapsed_ms,
            error_message=error,
        )
    except Exception as e:
        logger.warning(f"[A2A] 网关日志写入失败：{e}")

    return fence_response(data, meta={"elapsed_ms": elapsed_ms})


# ===== 接口 =====

@router.post("/register")
async def a2a_register(
    req: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """注册外部 Agent，返回 API Key（只显示一次）"""
    result, err = await register_agent(
        db, req.name, req.developer, req.business_id, req.rate_limit_per_min,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)
    return success_response(result, request_id=request.state.request_id)


@router.get("/capabilities")
async def a2a_capabilities(
    request: Request,
    agent=Depends(get_a2a_agent),
    db: AsyncSession = Depends(get_db),
):
    """能力发现"""
    start = time.time()
    business = await get_business_for_agent(db, agent)
    business_id = business.id if business else 0
    data = get_capabilities(business_id)
    return await _log_and_fence(request, db, agent, business_id, start, data)


@router.get("/products")
async def a2a_products(
    request: Request,
    keyword: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    agent=Depends(get_a2a_agent),
    db: AsyncSession = Depends(get_db),
):
    """搜索商品"""
    start = time.time()
    business = await get_business_for_agent(db, agent)
    business_id = business.id if business else 0
    data = await search_products(db, business_id, keyword, category, brand, page, page_size)
    return await _log_and_fence(request, db, agent, business_id, start, data)


@router.get("/products/{sku_id}")
async def a2a_product_detail(
    sku_id: str,
    request: Request,
    agent=Depends(get_a2a_agent),
    db: AsyncSession = Depends(get_db),
):
    """商品详情"""
    start = time.time()
    business = await get_business_for_agent(db, agent)
    business_id = business.id if business else 0
    data = await get_product_detail_a2a(db, business_id, sku_id)
    if data is None:
        return await _log_and_fence(request, db, agent, business_id, start, None, status_code=404, error="商品不存在")
    return await _log_and_fence(request, db, agent, business_id, start, data)


@router.get("/inventory")
async def a2a_inventory(
    request: Request,
    keyword: Optional[str] = Query(None),
    sku_code: Optional[str] = Query(None),
    stock_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    agent=Depends(get_a2a_agent),
    db: AsyncSession = Depends(get_db),
):
    """库存查询"""
    start = time.time()
    business = await get_business_for_agent(db, agent)
    business_id = business.id if business else 0
    data = await search_inventory(db, business_id, keyword, sku_code, stock_status, page, page_size)
    return await _log_and_fence(request, db, agent, business_id, start, data)


@router.post("/orders")
async def a2a_create_order(
    req: A2ACreateOrderRequest,
    request: Request,
    agent=Depends(get_a2a_agent),
    db: AsyncSession = Depends(get_db),
):
    """创建订单"""
    start = time.time()
    business = await get_business_for_agent(db, agent)
    business_id = business.id if business else 0

    # 转换为内部 CreateOrderRequest 格式
    order_data = {
        "items": [
            {"sku_id": it.sku_id, "qty": it.qty, "unit_price": it.unit_price}
            for it in req.items
        ],
        "customer_id": req.customer_id,
        "customer_info": req.customer_info.model_dump() if req.customer_info else None,
        "remark": req.remark,
    }
    data, err = await create_order_a2a(db, business_id, agent.id, order_data)
    if err:
        return await _log_and_fence(request, db, agent, business_id, start, None, status_code=400, error=err)
    return await _log_and_fence(request, db, agent, business_id, start, data)


@router.get("/orders/{order_no}")
async def a2a_get_order(
    order_no: str,
    request: Request,
    agent=Depends(get_a2a_agent),
    db: AsyncSession = Depends(get_db),
):
    """查询订单"""
    start = time.time()
    business = await get_business_for_agent(db, agent)
    business_id = business.id if business else 0
    data, err = await get_order_a2a(db, business_id, order_no)
    if err:
        return await _log_and_fence(request, db, agent, business_id, start, None, status_code=404, error=err)
    return await _log_and_fence(request, db, agent, business_id, start, data)
