"""FastAPI 应用入口

M6-3 改进：
- /health 轻量存活检查（liveness）
- /ready 就绪检查（含 DB/Redis 实际 ping）
- lifespan 中 scheduler.start() 失败不应阻断启动（仅告警），但 DB 初始化失败必须 fail-fast
- SlowRequestMiddleware 记录慢请求
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from app.api.response import (
    RequestContextMiddleware,
    biz_exception_handler,
    generic_exception_handler,
    validation_exception_handler,
    BizException,
)
from app.config import settings
from app.database import check_db_health, close_db, init_db
from app.redis_client import RedisClient
from app.agent.loop.scheduler import get_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    # 启动
    try:
        await init_db()
    except Exception as e:
        logger.error(f"[Lifespan] 数据库初始化失败，终止启动：{e}", exc_info=True)
        raise

    # 启动 OUPDEL 循环调度器（失败仅告警，不阻断 HTTP 服务）
    scheduler = get_scheduler()
    try:
        scheduler.start()
    except Exception as e:
        logger.warning(f"[Lifespan] OUPDEL 调度器启动失败（不阻断 HTTP）：{e}", exc_info=True)

    yield

    # 关闭
    try:
        await scheduler.stop()
    except Exception as e:
        logger.warning(f"[Lifespan] 调度器停止异常：{e}", exc_info=True)
    await close_db()
    await RedisClient.close()


class SlowRequestMiddleware:
    """慢请求日志中间件 - 超过阈值记录 warning"""

    def __init__(self, app, threshold_ms: int = 1000):
        self.app = app
        self.threshold_ms = threshold_ms

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        start = time.time()
        try:
            await self.app(scope, receive, send)
        finally:
            elapsed_ms = int((time.time() - start) * 1000)
            if elapsed_ms > self.threshold_ms:
                path = scope.get("path", "")
                method = scope.get("method", "")
                logger.warning(
                    f"[SlowRequest] {method} {path} took {elapsed_ms}ms (threshold={self.threshold_ms}ms)"
                )


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    show_docs = settings.is_dev or settings.DOCS_ENABLED
    app = FastAPI(
        title="AIOW API",
        description="AI Operating World - 自治零售门店操作系统",
        version="1.0.0",
        docs_url="/docs" if show_docs else None,
        redoc_url="/redoc" if show_docs else None,
        openapi_url="/openapi.json" if show_docs else None,
        lifespan=lifespan,
    )

    # 中间件（顺序：后加的先执行）
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    # 慢请求监控
    if settings.SLOW_REQUEST_THRESHOLD_MS > 0:
        app.add_middleware(SlowRequestMiddleware, threshold_ms=settings.SLOW_REQUEST_THRESHOLD_MS)

    # 异常处理器
    app.add_exception_handler(BizException, biz_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    # ===== 存活检查（轻量，不查依赖）=====
    @app.get("/health", tags=["系统"])
    async def health_check():
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "status": "healthy",
                "env": settings.APP_ENV,
                "version": "1.0.0",
            },
        }

    # ===== 就绪检查（查 DB + Redis，K8s readinessProbe 使用）=====
    @app.get("/ready", tags=["系统"])
    async def readiness_check():
        db_ok = await check_db_health()
        redis_ok = await RedisClient.health_check()
        ready = db_ok and redis_ok
        return {
            "code": 0 if ready else 1,
            "message": "ready" if ready else "not ready",
            "data": {
                "ready": ready,
                "checks": {
                    "database": "ok" if db_ok else "fail",
                    "redis": "ok" if redis_ok else "fail",
                },
                "env": settings.APP_ENV,
                "version": "1.0.0",
            },
        }

    # 注册 API 路由
    from app.api.v1.router import api_router
    app.include_router(api_router, prefix="/api/v1")

    # 注册监控路由（Prometheus metrics）- 挂在根路径 /metrics 便于 Prometheus 抓取
    if settings.METRICS_ENABLED:
        from app.api.v1.monitoring import router as metrics_router, metrics_middleware
        app.include_router(metrics_router, prefix="")
        # HTTP 指标收集中间件
        app.middleware("http")(metrics_middleware)

    return app


app = create_app()
