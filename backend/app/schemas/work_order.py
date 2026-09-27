"""工单 Pydantic schemas"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class WorkOrderCreate(BaseModel):
    """Agent 创建工单"""
    order_type: str = Field(..., max_length=32, description="操作类型（price_adjust/stock_in/stock_out/refund/purchase_suggestion）")
    title: str = Field(..., max_length=256, description="工单标题")
    description: Optional[str] = Field(None, description="详细描述")
    reason: Optional[str] = Field(None, description="发起原因")
    expected_effect: Optional[str] = Field(None, description="预期效果")
    risk_level: str = Field("medium", max_length=8, description="风险等级 low/medium/high")
    params: Optional[dict] = Field(None, description="操作参数（工具调用 input）")


class ApprovalRequest(BaseModel):
    """审批请求"""
    comment: Optional[str] = Field(None, max_length=1000, description="审批意见")
    modified_params: Optional[dict] = Field(None, description="修改后的参数（审批通过时可改）")


class CancelRequest(BaseModel):
    """取消请求"""
    comment: Optional[str] = Field(None, max_length=1000, description="取消原因")


class ExecutionResult(BaseModel):
    """执行结果回写"""
    result: str = Field(..., description="执行结果摘要")
    is_success: bool = Field(True, description="是否成功")
    error_message: Optional[str] = Field(None, description="失败原因")


class WorkOrderOut(BaseModel):
    """工单详情"""
    id: int
    business_id: int
    agent_id: int
    order_type: str
    title: str
    description: Optional[str] = None
    reason: Optional[str] = None
    expected_effect: Optional[str] = None
    risk_level: str
    params: dict = {}
    status: str
    submitter_agent_id: Optional[int] = None
    approver_id: Optional[int] = None
    approved_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
