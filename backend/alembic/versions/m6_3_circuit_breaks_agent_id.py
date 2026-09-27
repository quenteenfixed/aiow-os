"""M6-3: circuit_breaks 增加 agent_id 列 + 索引

为 agent 级熔断提供精确匹配列，替代 trigger_condition 字符串 like 子串匹配（修复 P0 假阳性）。
同时为已存在的 agent 级熔断记录回填 agent_id（从 trigger_condition 中解析 agent:{id} 标记）。

Revision ID: m6_3_circuit_breaks_agent_id
Revises: m4_1_memory_expires_at
Create Date: 2026-09-27
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = 'm6_3_circuit_breaks_agent_id'
down_revision: Union[str, None] = 'm4_1_memory_expires_at'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # 1) 新增 agent_id 列（NULL 表示 system 级）
    op.add_column(
        'circuit_breaks',
        sa.Column('agent_id', sa.BigInteger(), nullable=True),
    )
    # 2) 索引
    op.create_index(
        'idx_circuit_breaks_biz_agent_status',
        'circuit_breaks',
        ['business_id', 'agent_id', 'status'],
    )
    # 3) 回填：把 trigger_condition 中编码的 agent:{id} 解析到 agent_id 列
    #    trigger_condition 格式如 "loss_threshold|agent:42"
    op.execute("""
        UPDATE circuit_breaks
        SET agent_id = SUBSTRING(trigger_condition FROM 'agent:(\\\\d+)')::bigint
        WHERE trigger_condition LIKE '%agent:%'
          AND level = 'agent'
          AND agent_id IS NULL
    """)
    # 4) 数据校验：清理 trigger_condition，去掉冗余的 agent:N 标记（保留 trigger_type）
    op.execute("""
        UPDATE circuit_breaks
        SET trigger_condition = SPLIT_PART(trigger_condition, '|', 1)
        WHERE trigger_condition LIKE '%|agent:%'
    """)


def downgrade() -> None:
    op.drop_index('idx_circuit_breaks_biz_agent_status', table_name='circuit_breaks')
    op.drop_column('circuit_breaks', 'agent_id')
