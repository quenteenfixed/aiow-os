"""Agent Pydantic schemas"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ===== 创建/更新 =====

class AgentCreate(BaseModel):
    """创建 Agent"""
    name: str = Field(..., max_length=64, description="Agent 名称")
    role: str = Field("store_manager", max_length=32, description="角色")
    avatar: Optional[str] = Field(None, max_length=512, description="头像 URL")
    autonomy_level: str = Field("L2", description="自治级别 L0-L4")
    model: Optional[str] = Field(None, max_length=64, description="LLM 模型，留空使用系统默认 (deepseek-flash)")
    system_prompt_text: Optional[str] = Field(None, description="自定义系统提示词，留空用默认")
    config: Optional[dict] = Field(None, description="额外配置")
    allowed_tools: List[str] = Field(
        default_factory=lambda: ["search_products", "get_inventory", "list_orders", "get_order_detail"],
        description="允许调用的工具白名单",
    )


class AgentUpdate(BaseModel):
    """更新 Agent"""
    name: Optional[str] = Field(None, max_length=64)
    avatar: Optional[str] = Field(None, max_length=512)
    autonomy_level: Optional[str] = Field(None, description="L0-L4")
    status: Optional[str] = Field(None, description="initializing/ready/running/paused/stopped/error")
    model: Optional[str] = Field(None, max_length=64)
    system_prompt_text: Optional[str] = None
    config: Optional[dict] = None
    allowed_tools: Optional[List[str]] = None


# ===== 输出 =====

class AgentOut(BaseModel):
    """Agent 详情"""
    id: int
    business_id: int
    name: str
    role: str
    avatar: Optional[str] = None
    autonomy_level: str
    status: str
    model: Optional[str] = None
    system_prompt_text: Optional[str] = None
    config: dict = {}
    allowed_tools: List[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SessionOut(BaseModel):
    """会话信息"""
    id: int
    agent_id: int
    session_type: str
    title: Optional[str] = None
    status: str
    context_summary: Optional[str] = None
    closed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MessageOut(BaseModel):
    """单条消息"""
    id: int
    session_id: int
    role: str
    content: Optional[str] = None
    tool_calls: Optional[dict] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    created_at: Optional[datetime] = None


# ===== 聊天 =====

class SessionCreate(BaseModel):
    """创建会话"""
    title: Optional[str] = Field(None, max_length=200, description="会话标题，留空自动生成")
    session_type: str = Field("chat", max_length=32, description="会话类型")


class ChatRequest(BaseModel):
    """聊天请求"""
    message: str = Field(..., min_length=1, max_length=4000, description="用户消息")
    session_id: Optional[int] = Field(None, description="会话 ID，无则新建")


class ChatResponse(BaseModel):
    """聊天响应"""
    session_id: int
    status: str = "completed"
    message: str
    loop_count: int = 0
    tool_call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
