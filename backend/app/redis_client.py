"""Redis 客户端 - 异步连接池"""
import logging
from typing import Optional

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis 异步客户端单例"""

    _instance: Optional[redis.Redis] = None
    _available: bool = True

    @classmethod
    def get_client(cls) -> Optional[redis.Redis]:
        """获取 Redis 客户端"""
        if not cls._available:
            return None
        if cls._instance is None:
            try:
                cls._instance = redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    encoding="utf-8",
                    max_connections=20,
                    socket_timeout=2,
                    socket_connect_timeout=2,
                    retry_on_timeout=True,
                )
            except Exception as e:
                logger.warning(f"Redis 连接失败，降级运行: {e}")
                cls._available = False
                return None
        return cls._instance

    @classmethod
    async def close(cls) -> None:
        """关闭连接"""
        if cls._instance is not None:
            await cls._instance.close()
            cls._instance = None

    @classmethod
    async def health_check(cls) -> bool:
        """检查 Redis 是否可用"""
        client = cls.get_client()
        if client is None:
            return False
        try:
            await client.ping()
            return True
        except Exception:
            cls._available = False
            return False


def get_redis() -> Optional[redis.Redis]:
    """获取 Redis 客户端"""
    return RedisClient.get_client()


async def add_token_to_blacklist(token: str, expire_seconds: int) -> None:
    """将 token 加入黑名单（Redis 不可用时静默跳过）"""
    client = get_redis()
    if client is None:
        return
    try:
        key = f"blacklist:token:{token}"
        await client.set(key, "1", ex=expire_seconds)
    except Exception as e:
        logger.warning(f"Redis 写入黑名单失败: {e}")


async def is_token_blacklisted(token: str) -> bool:
    """检查 token 是否在黑名单（Redis 不可用时返回 False，放行）"""
    client = get_redis()
    if client is None:
        return False
    try:
        result = await client.get(f"blacklist:token:{token}")
        return result is not None
    except Exception as e:
        logger.warning(f"Redis 查询黑名单失败: {e}")
        return False


async def check_rate_limit(
    key: str, max_count: int, window_seconds: int
) -> tuple[bool, int]:
    """滑动窗口限流 - 返回 (是否允许, 当前计数)"""
    import time

    client = get_redis()
    if client is None:
        return True, 0  # Redis 不可用时不限流

    now = int(time.time())
    pipe = client.pipeline()
    pipe.zremrangebyscore(key, 0, now - window_seconds)
    pipe.zadd(key, {str(now): now})
    pipe.zcard(key)
    pipe.expire(key, window_seconds)

    try:
        results = await pipe.execute()
        count = results[2]
        return count <= max_count, count
    except Exception as e:
        logger.warning(f"Redis 限流失败: {e}")
        return True, 0
