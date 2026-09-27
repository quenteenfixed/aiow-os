"""应用配置 - 基于 pydantic-settings 从环境变量加载

生产环境（APP_ENV=production）强制安全约束：
- JWT_SECRET 不得使用默认占位值（启动期 fail-fast）
- CORS 来源需显式配置，不使用通配 "*"
"""
from functools import lru_cache
from typing import List

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_DEFAULT_JWT_SECRET = "change-me-in-production-please-use-a-long-random-string"


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ===== App =====
    APP_ENV: str = "development"
    LOG_LEVEL: str = "info"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8080"
    DOCS_ENABLED: bool = False

    # ===== Database =====
    DATABASE_URL: str = "postgresql+asyncpg://aiow:aiow@localhost:5432/aiow"
    DATABASE_SYNC_URL: str = "postgresql+psycopg2://aiow:aiow@localhost:5432/aiow"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 3600
    DB_ECHO: bool = False
    DB_SSL_MODE: str = ""

    # ===== Redis =====
    REDIS_URL: str = "redis://localhost:6379/0"

    # ===== LLM =====
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-flash"
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20240620"

    # ===== JWT =====
    JWT_SECRET: str = _DEFAULT_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ===== A2A 限流 =====
    A2A_RATE_LIMIT_REDIS: bool = False

    # ===== 监控 =====
    METRICS_ENABLED: bool = True
    SLOW_REQUEST_THRESHOLD_MS: int = 1000

    @field_validator("CORS_ORIGINS")
    @classmethod
    def parse_cors_origins(cls, v: str) -> str:
        return v

    @model_validator(mode="after")
    def _enforce_prod_safety(self) -> "Settings":
        if self.APP_ENV == "production":
            if not self.JWT_SECRET or self.JWT_SECRET == _DEFAULT_JWT_SECRET or len(self.JWT_SECRET) < 32:
                raise RuntimeError(
                    "生产环境 APP_ENV=production 必须设置 JWT_SECRET（>=32 字符且非默认占位值）"
                )
            if "*" in self.cors_origins_list:
                raise RuntimeError("生产环境 CORS_ORIGINS 不允许使用通配 *")
        return self

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_dev(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def is_test(self) -> bool:
        return self.APP_ENV == "test"

    @property
    def is_prod(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
