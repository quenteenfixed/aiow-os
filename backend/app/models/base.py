"""模型基类与混入"""
from datetime import datetime
from typing import Optional

import uuid as uuid_lib
from sqlalchemy import BigInteger, DateTime, func, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """时间戳 - created_at / updated_at（updated_at 由触发器自动维护）"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """软删除 - deleted_at"""

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        default=None,
        nullable=True,
    )


class UUIDMixin:
    """对外 UUID 列（03-api-spec §1.7 要求对外用 UUID）"""

    uuid: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        nullable=False,
        unique=True,
        index=True,
    )
