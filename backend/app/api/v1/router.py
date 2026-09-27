"""API v1 路由聚合"""
from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.business import router as business_router
from app.api.v1.inventory import router as inventory_router
from app.api.v1.order import router as order_router
from app.api.v1.product import router as product_router, sku_router
from app.api.v1.customer import router as customer_router
from app.api.v1.agent import router as agent_router
from app.api.v1.work_order import router as work_order_router
from app.api.v1.loop import router as loop_router
from app.api.v1.alert import router as alert_router
from app.api.v1.memory import router as memory_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.a2a import router as a2a_router
from app.api.v1.circuit_breaker import router as circuit_router
from app.api.v1.audit import router as audit_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["认证"])
api_router.include_router(business_router, prefix="/businesses", tags=["商业实体"])
api_router.include_router(product_router, prefix="/products", tags=["商品"])
api_router.include_router(sku_router, prefix="/skus", tags=["SKU"])
api_router.include_router(inventory_router, prefix="/inventory", tags=["库存"])
api_router.include_router(order_router, prefix="/orders", tags=["订单"])
api_router.include_router(customer_router, prefix="/customers", tags=["客户"])
api_router.include_router(agent_router, prefix="/agents", tags=["Agent"])
api_router.include_router(work_order_router, prefix="/work-orders", tags=["工单"])
api_router.include_router(loop_router, prefix="/loops", tags=["OUPDEL 循环"])
api_router.include_router(alert_router, prefix="/alerts", tags=["告警"])
api_router.include_router(memory_router, prefix="/memories", tags=["记忆"])
api_router.include_router(feedback_router, prefix="/feedback", tags=["反馈学习"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["仪表盘"])
api_router.include_router(a2a_router, prefix="/a2a", tags=["A2A 网关"])
api_router.include_router(circuit_router, prefix="/circuit-breaker", tags=["熔断系统"])
api_router.include_router(audit_router, prefix="/audit", tags=["审计日志"])
