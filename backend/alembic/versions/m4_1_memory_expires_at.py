"""M4-1: agent_memories 增加 expires_at 字段 + 索引

Revision ID: m4_1_memory_expires_at
Revises: m3_3_agent_loops
Create Date: 2026-09-27
"""
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = 'm4_1_memory_expires_at'
down_revision: Union[str, None] = 'm3_3_agent_loops'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        'agent_memories',
        sa.Column('expires_at', sa.DateTime(), nullable=True),
    )
    op.create_index('idx_agent_memories_expires_at', 'agent_memories', ['expires_at'])


def downgrade() -> None:
    op.drop_index('idx_agent_memories_expires_at', table_name='agent_memories')
    op.drop_column('agent_memories', 'expires_at')
