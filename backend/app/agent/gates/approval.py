"""Approval Gate - 审批门禁，高风险写入操作进入审批流程

风险分级：
- low（低风险）：自动执行，无需审批。如：查库存、查订单
- medium（中风险）：执行后通知店主。如：小额调价、临期商品下架
- high（高风险）：必须审批后执行。如：大额订单、批量删除、调价超阈值

M2-3 scaffold 说明：
- WorkOrder 表在 M3-1 工单系统才创建，M2-3 先不真正写库。
- Approval Gate 返回 needs_approval=True，由 Executor 决定如何处理：
  - M2-3：返回 pending_approval 状态给前端，不执行工具
  - M3-1+：真正创建 WorkOrder 记录，关联到 agent_messages
- 风险判定规则由 TOOL_RISK_CONFIG 配置，M3-2 写入工具上线后扩充。
"""
import logging

from app.agent.types import ToolCall, SessionContext, GateResult

logger = logging.getLogger(__name__)

# 工具风险等级配置（M3-2 写入工具上线后扩充）
# 未配置的工具默认 risk_level="low"
TOOL_RISK_CONFIG: dict = {
    # "update_stock": {"risk_level": "medium", "auto_approve_below": 100},
    # "create_order": {"risk_level": "high", "auto_approve_below": 500},
    # "delete_product": {"risk_level": "high"},
    # "adjust_price": {"risk_level": "medium", "auto_approve_below": 0.2},
}

# 全局阈值：高风险操作一律需审批
HIGH_RISK_THRESHOLD = "high"


class ApprovalGate:
    """Approval Gate - 审批门禁

    对写入类工具做风险评估，高风险操作返回 needs_approval=True。
    """

    def __init__(self, work_order_creator=None):
        """
        Args:
            work_order_creator: 可选的工单创建回调（M3-1 接入后传入）。
                签名：async def creator(db, ctx, tool_call, risk_level, reason) -> int
                返回 work_order_id。M2-3 阶段为 None，不真正创建工单。
        """
        self._work_order_creator = work_order_creator

    async def check(
        self,
        tool_call: ToolCall,
        ctx: SessionContext,
        db=None,
    ) -> GateResult:
        """评估写入操作风险，高风险需审批"""
        risk_config = TOOL_RISK_CONFIG.get(tool_call.name, {})
        risk_level = risk_config.get("risk_level", "low")

        # 低风险：直接放行
        if risk_level == "low":
            return GateResult(
                passed=True, reason="", gate_name="approval",
                risk_level="low",
            )

        # 中高风险：检查是否满足自动审批条件
        auto_approve_below = risk_config.get("auto_approve_below")
        if auto_approve_below is not None:
            # 简化：取工具参数中第一个数值型字段做阈值判断
            param_value = self._extract_numeric_param(tool_call)
            if param_value is not None and param_value <= auto_approve_below:
                return GateResult(
                    passed=True, reason="", gate_name="approval",
                    risk_level=risk_level,
                )

        # 高风险：需审批
        reason = (
            f"工具 {tool_call.name} 为 {risk_level} 风险写入操作，"
            f"需店主审批后执行。"
        )
        logger.info(
            f"[ApprovalGate] 工具 {tool_call.name}（call_id={tool_call.id}）"
            f"触发审批：{reason}"
        )

        # M3-1+ 接入后真正创建工单
        work_order_id = None
        if self._work_order_creator and db is not None:
            try:
                work_order_id = await self._work_order_creator(
                    db, ctx, tool_call, risk_level, reason,
                )
                logger.info(f"[ApprovalGate] 已创建工单 #{work_order_id}")
            except Exception as e:
                logger.error(f"[ApprovalGate] 创建工单失败：{e}")

        return GateResult(
            passed=True,  # 门禁本身不拦截，但 needs_approval=True
            reason=reason,
            gate_name="approval",
            needs_approval=True,
            risk_level=risk_level,
            metadata={
                "work_order_id": work_order_id,
                "tool_name": tool_call.name,
            },
        )

    def _extract_numeric_param(self, tool_call: ToolCall):
        """从工具参数中提取数值字段（用于阈值判断）"""
        params = tool_call.input or {}
        for key in ("quantity", "total_amount", "amount", "price_delta"):
            if key in params:
                try:
                    return float(params[key])
                except (TypeError, ValueError):
                    continue
        return None
