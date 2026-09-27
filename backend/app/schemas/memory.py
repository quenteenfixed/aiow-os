"""记忆系统 Pydantic schemas

记忆分类：
- fact      : 事实记忆（客观数据，如"商品A库存100"）
- preference: 偏好记忆（用户偏好，如"店主喜欢每周一补货"）
- action    : 操作记忆（历史操作记录）
- feedback  : 反馈记忆（审批拒绝原因、用户纠正等）

重要程度：1（临时）~ 5（非常重要）。importance=1 的记忆自动设置 expires_at。
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class MemoryCreate(BaseModel):
    """创建记忆"""
    memory_type: str = Field("fact", description="记忆类型：fact/preference/action/feedback")
    title: str = Field(..., max_length=256, description="记忆标题")
    content: str = Field(..., description="记忆内容")
    tags: Optional[List[str]] = Field(None, description="标签列表")
    importance: int = Field(3, ge=1, le=5, description="重要程度 1-5，1=临时，5=非常重要")
    source: Optional[str] = Field("manual", max_length=32, description="来源：manual/agent/loop/feedback")
    source_id: Optional[int] = Field(None, description="关联来源 ID")
    ttl_hours: Optional[int] = Field(None, ge=1, le=8760, description="临时记忆的过期时间（小时），不传则永久")


class MemoryUpdate(BaseModel):
    """更新记忆"""
    title: Optional[str] = Field(None, max_length=256)
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    importance: Optional[int] = Field(None, ge=1, le=5)


class MemorySearch(BaseModel):
    """记忆检索"""
    query: str = Field(..., description="检索关键词")
    memory_type: Optional[str] = Field(None, description="按类型筛选")
    tags: Optional[List[str]] = Field(None, description="按标签筛选")
    top_k: int = Field(5, ge=1, le=50, description="返回结果数")


class MemoryOut(BaseModel):
    """记忆详情"""
    id: int
    agent_id: int
    business_id: int
    memory_type: str
    title: str
    content: str
    tags: List[str] = []
    importance: int = 3
    source: Optional[str] = None
    source_id: Optional[int] = None
    metadata_: dict = {}
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # 检索时计算的相关度分数（0-1）
    relevance_score: Optional[float] = None
