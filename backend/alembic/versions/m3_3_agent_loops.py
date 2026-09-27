"""M3-3: agent_loops + agent_loop_runs 表

Revision ID: m3_3_agent_loops
Revises: f3581f07aaab
Create Date: 2026-09-27
"""
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'm3_3_agent_loops'
down_revision: Union[str, None] = 'f3581f07aaab'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # 1. agent_loops - 循环配置
    op.create_table(
        'agent_loops',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('business_id', sa.BigInteger(), sa.ForeignKey('businesses.id'), nullable=False),
        sa.Column('agent_id', sa.BigInteger(), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False, server_default='default_loop'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('interval_minutes', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('sensitivity', sa.String(length=8), nullable=False, server_default='medium'),
        sa.Column('autonomy_level', sa.String(length=8), nullable=False, server_default='L2'),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('last_run_at', sa.DateTime(), nullable=True),
        sa.Column('next_run_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('uk_agent_loops_agent_id', 'agent_loops', ['agent_id'], unique=True)
    op.create_index('idx_agent_loops_biz_enabled', 'agent_loops', ['business_id', 'enabled'])
    op.create_index('idx_agent_loops_next_run', 'agent_loops', ['next_run_at'])

    # 2. agent_loop_runs - 运行记录
    op.create_table(
        'agent_loop_runs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('loop_id', sa.BigInteger(), sa.ForeignKey('agent_loops.id', ondelete='CASCADE'), nullable=False),
        sa.Column('business_id', sa.BigInteger(), sa.ForeignKey('businesses.id'), nullable=False),
        sa.Column('agent_id', sa.BigInteger(), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('trigger_type', sa.String(length=16), nullable=False, server_default='scheduled'),
        sa.Column('run_status', sa.String(length=16), nullable=False, server_default='running'),
        sa.Column('started_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('observe_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('anomalies', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('anomaly_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('plans', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('decisions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('work_order_ids', postgresql.ARRAY(sa.BigInteger()), server_default='{}', nullable=True),
        sa.Column('work_order_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('evaluation', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_agent_loop_runs_loop_created', 'agent_loop_runs', ['loop_id', 'created_at'])
    op.create_index('idx_agent_loop_runs_biz_status', 'agent_loop_runs', ['business_id', 'run_status'])
    op.create_index('idx_agent_loop_runs_agent_created', 'agent_loop_runs', ['agent_id', 'created_at'])
    op.create_index('idx_agent_loop_runs_run_status', 'agent_loop_runs', ['run_status'])


def downgrade() -> None:
    op.drop_index('idx_agent_loop_runs_run_status', table_name='agent_loop_runs')
    op.drop_index('idx_agent_loop_runs_agent_created', table_name='agent_loop_runs')
    op.drop_index('idx_agent_loop_runs_biz_status', table_name='agent_loop_runs')
    op.drop_index('idx_agent_loop_runs_loop_created', table_name='agent_loop_runs')
    op.drop_table('agent_loop_runs')

    op.drop_index('idx_agent_loops_next_run', table_name='agent_loops')
    op.drop_index('idx_agent_loops_biz_enabled', table_name='agent_loops')
    op.drop_index('uk_agent_loops_agent_id', table_name='agent_loops')
    op.drop_table('agent_loops')
