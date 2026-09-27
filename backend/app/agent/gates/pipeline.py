"""Gate Pipeline - 门禁编排器，按顺序执行 5 道门禁

执行顺序（read 工具只跑 1,5；write 工具跑全部 5 道）：
1. Fencing Gate    - 围栏标记检测（防 prompt injection）
2. Provenance Gate - 来源校验（防越权 ID，仅 write）
3. Guardrail Gate  - 参数护栏（防危险参数）
4. Rate Limit Gate  - 频率限制
5. Approval Gate   - 审批门禁（仅 write，高风险需审批）

任一门禁 block → 立即终止，返回 block 决策。
Approval Gate 返回 needs_approval=True → 返回 pending_approval 决策。
全部通过 → 返回 pass 决策。
"""
import logging
import time
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.gates.fencing import FencingGate
from app.agent.gates.rate_limit import get_rate_limit_gate
from app.agent.gates.provenance import ProvenanceGate
from app.agent.gates.guardrail import GuardrailGate
from app.agent.gates.approval import ApprovalGate
from app.agent.types import (
    GateResult, PipelineResult, SessionContext, ToolCall, ToolDefinition,
)

logger = logging.getLogger(__name__)

# 门禁执行顺序（固定）
GATE_ORDER = ["fencing", "provenance", "guardrail", "rate_limit", "approval"]


class GatePipeline:
    """门禁管线 - 编排 5 道门禁的顺序执行

    线程安全：所有 Gate 都是无状态或单例，Pipeline 本身无状态。
    """

    def __init__(
        self,
        fencing_gate: Optional[FencingGate] = None,
        provenance_gate: Optional[ProvenanceGate] = None,
        guardrail_gate: Optional[GuardrailGate] = None,
        rate_limit_gate=None,
        approval_gate: Optional[ApprovalGate] = None,
    ):
        self.fencing = fencing_gate or FencingGate()
        self.provenance = provenance_gate or ProvenanceGate()
        self.guardrail = guardrail_gate or GuardrailGate()
        self.rate_limit = rate_limit_gate or get_rate_limit_gate()
        self.approval = approval_gate or ApprovalGate()

    async def check(
        self,
        tool_call: ToolCall,
        ctx: SessionContext,
        tool_def: Optional[ToolDefinition] = None,
        db: Optional[AsyncSession] = None,
    ) -> PipelineResult:
        """按顺序执行门禁，返回最终决策

        Args:
            tool_call: 工具调用
            ctx: 会话上下文
            tool_def: 工具定义（用于判断 category 与 gates 配置）
            db: 数据库会话（供 Approval Gate 创建工单用）
        Returns:
            PipelineResult(decision="pass"/"block"/"pending_approval")
        """
        start = time.time()

        # 确定工具分类与门禁配置
        category = tool_def.category if tool_def else "read"
        gates_config = self._resolve_gates_config(tool_def, category)

        for gate_name in GATE_ORDER:
            # 该门禁是否启用？
            if not gates_config.get(gate_name, False):
                continue

            # 执行门禁
            gate_result = await self._run_gate(
                gate_name, tool_call, ctx, db=db,
            )

            # 拦截：立即终止
            if not gate_result.passed:
                elapsed_ms = int((time.time() - start) * 1000)
                logger.info(
                    f"[Pipeline] 工具 {tool_call.name} 被 {gate_name} 拦截"
                    f"（{elapsed_ms}ms）：{gate_result.reason}"
                )
                return PipelineResult(
                    decision="block",
                    reason=gate_result.reason,
                    gate_name=gate_name,
                    risk_level=gate_result.risk_level,
                    metadata={
                        "total_elapsed_ms": elapsed_ms,
                        **gate_result.metadata,
                    },
                )

            # 审批挂起：返回 pending_approval
            if gate_result.needs_approval:
                elapsed_ms = int((time.time() - start) * 1000)
                logger.info(
                    f"[Pipeline] 工具 {tool_call.name} 触发审批"
                    f"（{gate_result.risk_level}，{elapsed_ms}ms）"
                )
                return PipelineResult(
                    decision="pending_approval",
                    reason=gate_result.reason,
                    gate_name=gate_name,
                    risk_level=gate_result.risk_level,
                    metadata={
                        "total_elapsed_ms": elapsed_ms,
                        "work_order_id": gate_result.metadata.get("work_order_id"),
                        **gate_result.metadata,
                    },
                )

        # 全部通过
        elapsed_ms = int((time.time() - start) * 1000)
        logger.debug(
            f"[Pipeline] 工具 {tool_call.name} 全部门禁通过（{elapsed_ms}ms）"
        )
        return PipelineResult(
            decision="pass",
            reason="",
            gate_name="",
            metadata={"total_elapsed_ms": elapsed_ms},
        )

    def _resolve_gates_config(
        self, tool_def: Optional[ToolDefinition], category: str
    ) -> dict:
        """解析门禁配置：分类缺省 + 工具显式覆盖

        关键：只应用 tool_def.gates 中显式出现的键（值 True/False），
        未出现的键沿用分类缺省。避免 dataclass 默认值误覆盖分类缺省。
        """
        # 分类缺省
        if category == "write":
            default = {
                "fencing": True, "provenance": True,
                "guardrail": True, "rate_limit": True, "approval": True,
            }
        else:
            default = {
                "fencing": True, "provenance": False,
                "guardrail": True, "rate_limit": True, "approval": False,
            }

        # 工具显式覆盖（只应用 tool_def.gates 中存在的键）
        if tool_def and tool_def.gates:
            for gate_name, enabled in tool_def.gates.items():
                default[gate_name] = enabled
        return default

    async def _run_gate(
        self,
        gate_name: str,
        tool_call: ToolCall,
        ctx: SessionContext,
        db: Optional[AsyncSession] = None,
    ) -> GateResult:
        """执行单道门禁"""
        if gate_name == "fencing":
            return await self.fencing.check(tool_call, ctx)
        if gate_name == "provenance":
            return await self.provenance.check(tool_call, ctx)
        if gate_name == "guardrail":
            return await self.guardrail.check(tool_call, ctx)
        if gate_name == "rate_limit":
            return await self.rate_limit.check(tool_call, ctx)
        if gate_name == "approval":
            return await self.approval.check(tool_call, ctx, db=db)
        # 未知门禁：放行
        return GateResult(passed=True, reason="", gate_name=gate_name)


async def _default_work_order_creator(db, ctx, tool_call, risk_level, reason):
    """默认工单创建回调 - 调用 work_order_service 真正写库

    M3-1 接入：当 Approval Gate 触发时，自动创建 pending 状态的工单。
    M3-2 写入工具上线后，此回调会被实际调用。
    """
    from app.services.work_order_service import create_work_order
    wo = await create_work_order(
        db, ctx.business_id, ctx.agent_id,
        order_type=tool_call.name,
        title=f"Agent 提交：{tool_call.name}",
        reason=reason,
        risk_level=risk_level,
        params=tool_call.input,
        submitter_agent_id=ctx.agent_id,
    )
    return wo.id


# 全局单例
_pipeline_instance: Optional[GatePipeline] = None


def get_gate_pipeline() -> GatePipeline:
    """获取全局门禁管线单例"""
    global _pipeline_instance
    if _pipeline_instance is None:
        # M3-2：确保写入工具的门禁配置已注入
        try:
            from app.agent.tools.write_tools import configure_write_gates
            configure_write_gates()
        except ImportError:
            pass  # write_tools 尚未加载（M2-x 阶段）
        approval_gate = ApprovalGate(work_order_creator=_default_work_order_creator)
        _pipeline_instance = GatePipeline(approval_gate=approval_gate)
    return _pipeline_instance
