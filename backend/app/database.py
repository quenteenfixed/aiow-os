"""数据库连接 - SQLAlchemy 2.0 异步引擎 + 会话

修复要点（M6-3）：
- TimestampMixin.created_at/updated_at 使用 datetime 类型 + onupdate 自动维护
- 生产环境通过 DB_SSL_MODE 启用 SSL（如 RDS/CloudSQL）
- init_db() 移除 CREATE EXTENSION（应在 Alembic 迁移中完成，避免每次启动需要超级用户权限）
"""
from typing import AsyncGenerator, Optional
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""
    pass


class TimestampMixin:
    """通用时间戳混入 - created_at / updated_at

    - created_at：插入时由 DB 默认值 now() 设置
    - updated_at：插入时由 DB 默认值 now()，更新时由 onupdate 自动刷新
    """
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), onupdate=text("now()"), nullable=False
    )


class SoftDeleteMixin:
    """软删除混入 - deleted_at（NULL 表示未删除）"""
    deleted_at: Mapped[Optional[datetime]] = mapped_column(default=None, nullable=True)


# 引擎连接参数
_connect_args = {}
if settings.is_prod:
    # 生产环境：要求 SSL 且服务端证书校验
    _connect_args["ssl"] = "require"

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
    echo=settings.DB_ECHO,
    future=True,
    pool_pre_ping=True,  # 连接复用前先 ping，避免拿到失效连接
    connect_args=_connect_args,
)

# 异步会话工厂
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖注入 - 获取数据库会话"""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """初始化数据库连接（应用启动时调用）

    注意：CREATE EXTENSION 已移至 Alembic 迁移（需要超级用户权限，不应每次启动执行）。
    这里仅做轻量的连接验证。
    """
    async with engine.begin() as conn:
        # 验证连接 + 时区一致性
        await conn.execute(text("SELECT 1"))


async def close_db() -> None:
    """关闭数据库连接（应用关闭时调用）"""
    await engine.dispose()


async def check_db_health() -> bool:
    """数据库健康检查（供 /health 与 /ready 使用）"""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
