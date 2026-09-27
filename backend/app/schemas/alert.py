"""告警 Pydantic schemas"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AlertCreate(BaseModel):
    """内部创建告警（不直接暴露给前端，由系统调用）"""
    alert_type: str = Field(..., max_length=32, description="告警类型：inventory/sales/expiring/system")
    level: str = Field("P2", max_length=8, description="告警级别：P0/P1/P2/P3")
    title: str = Field(..., max_length=256, description="告警标题")
    content: Optional[str] = Field(None, description="告警内容")
    source: Optional[str] = Field("system", max_length=32, description="告警来源：system/agent/loop")
    dedup_window_hours: int = Field(24, ge=0, le=168, description="去重窗口（小时），0 表示不去重")


class AlertAcknowledge(BaseModel):
    """告警确认"""
    comment: Optional[str] = Field(None, max_length=1000, description="确认备注")


class AlertResolve(BaseModel):
    """告警解决"""
    comment: Optional[str] = Field(None, max_length=1000, description="解决备注")


class AlertOut(BaseModel):
    """告警详情"""
    id: int
    business_id: int
    alert_type: str
    level: str
    title: str
    content: Optional[str] = None
    source: Optional[str] = None
    status: str
    resolved_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
