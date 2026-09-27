"""OUPDEL 循环 Pydantic schemas"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ===== 循环配置 =====

class LoopCreate(BaseModel):
    """创建循环配置"""
    agent_id: int = Field(..., description="Agent ID")
    name: str = Field("default_loop", max_length=64, description="循环名称")
    enabled: bool = Field(True, description="是否启用")
    interval_minutes: int = Field(60, ge=5, le=1440, description="触发频率（分钟），最小 5，最大 1440")
    sensitivity: str = Field("medium", description="灵敏度：low/medium/high")
    autonomy_level: str = Field("L2", description="自主级别：L0/L1/L2/L3/L4")
    config: Optional[dict] = Field(None, description="自定义配置（阈值覆盖等）")


class LoopUpdate(BaseModel):
    """更新循环配置"""
    name: Optional[str] = Field(None, max_length=64)
    enabled: Optional[bool] = None
    interval_minutes: Optional[int] = Field(None, ge=5, le=1440)
    sensitivity: Optional[str] = Field(None)
    autonomy_level: Optional[str] = Field(None)
    config: Optional[dict] = None


class LoopOut(BaseModel):
    """循环配置详情"""
    id: int
    business_id: int
    agent_id: int
    name: str
    enabled: bool
    interval_minutes: int
    sensitivity: str
    autonomy_level: str
    config: dict = {}
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ===== 循环运行记录 =====

class LoopRunOut(BaseModel):
    """循环运行记录"""
    id: int
    loop_id: int
    business_id: int
    agent_id: int
    trigger_type: str
    run_status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    observe_data: Optional[dict] = None
    anomalies: Optional[list] = None
    anomaly_count: int = 0
    plans: Optional[list] = None
    decisions: Optional[list] = None
    work_order_ids: List[int] = []
    work_order_count: int = 0
    evaluation: Optional[dict] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None


class TriggerRequest(BaseModel):
    """手动触发循环"""
    trigger_type: str = Field("manual", description="触发方式：manual/test")
