"""Agent 运行时核心数据结构 - 会话上下文、工具调用、门禁结果等"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def utcnow_naive() -> datetime:
    """返回 naive UTC datetime（asyncpg + timestamptz 列要求）"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class TokenUsage:
    """Token 使用统计"""
    input: int = 0
    output: int = 0


@dataclass
class SessionContext:
    """会话上下文 - 一次 Agent 交互的核心载体

    持久化到 agent_sessions / agent_messages 表。
    read_set 追踪本次会话中读取过的对象 ID（供 Provenance Gate 用，M2-3 启用）。
    """
    session_id: int
    agent_id: int
    business_id: int
    session_type: str = "chat"
    title: Optional[str] = None
    status: str = "active"
    # 内存中的消息列表（Claude API 格式：role + content）
    messages: list = field(default_factory=list)
    # 读取过的对象 ID 集合（"product:<uuid>" / "order:<uuid>" 等）
    read_set: set = field(default_factory=set)
    tool_call_count: int = 0
    loop_count: int = 0
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    context_summary: Optional[str] = None


@dataclass
class ToolCall:
    """单次工具调用"""
    id: str
    name: str
    input: dict
    schema_version: str = "1.0"


@dataclass
class ToolResult:
    """工具执行结果"""
    tool_call_id: str
    tool_name: str
    content: Any  # 可为 str / dict / list
    is_error: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class GateResult:
    """门禁检查结果

    M2-3 扩展：
    - needs_approval=True 表示写入操作风险较高，需进入审批流程（不直接执行）
    - risk_level 标记风险等级（low/medium/high），供 Approval Gate 与日志用
    - metadata 透传额外信息（如建议的审批人、工单类型等）
    """
    passed: bool
    reason: str
    gate_name: str
    # M2-3：Approval Gate 用，True 表示放行但需先审批
    needs_approval: bool = False
    risk_level: str = "low"  # low / medium / high
    metadata: dict = field(default_factory=dict)


@dataclass
class PipelineResult:
    """门禁管线最终决策

    decision 取值：
    - "pass"：全部门禁通过，可执行工具
    - "block"：某道门禁拦截，返回错误给 LLM
    - "pending_approval"：审批门禁触发，不执行，创建工单
    """
    decision: str
    reason: str
    gate_name: str  # 做出最终决策的门禁名
    risk_level: str = "low"
    metadata: dict = field(default_factory=dict)


@dataclass
class ToolDefinition:
    """工具定义（Claude API tool format）"""
    name: str
    description: str
    input_schema: dict
    # 工具分类：read（查询类）/ write（写入类）
    category: str = "read"
    # 门禁配置（哪些门禁启用）。缺省空 dict，由 GatePipeline 按 category 推断：
    # read 工具 → fencing + guardrail + rate_limit；write 工具 → 全 5 道
    gates: dict = field(default_factory=dict)


@dataclass
class AgentResponse:
    """Agent 执行最终响应"""
    status: str = "completed"  # completed / pending_approval / error
    message: Optional[str] = None
    loop_count: int = 0
    tool_call_count: int = 0
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    error: Optional[str] = None
    session_id: Optional[int] = None
    # 流式场景下累积的全部助手文本
    full_text: Optional[str] = None
    approval_work_order_ids: list = field(default_factory=list)


@dataclass
class AgentConfig:
    """Agent 配置（运行时从 Agent 实例加载）"""
    agent_id: int
    business_id: int
    name: str
    role: str
    model: str
    autonomy_level: str = "L2"
    system_prompt_text: Optional[str] = None
    config: dict = field(default_factory=dict)
    # 允许调用的工具白名单
    allowed_tools: list = field(default_factory=list)
