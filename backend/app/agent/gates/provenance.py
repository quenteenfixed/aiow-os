"""Provenance Gate - 来源校验，防越权 ID

核心原理（参照 Anthropic Commerce Agents 的 "taint tracking" 思路）：
- 写入类工具参数中的对象 ID（product_id / order_id / customer_id / sku_id 等）
  必须来自本次会话中"读取类工具"已经查询过的结果集（ctx.read_set）。
- 若 LLM 凭空捏造一个 ID（未经查询直接写入），视为越权/幻觉，立即拦截。
- read_set 中的键格式为 "<类型>:<ID>"（如 "product:abc-123"），由 ToolExecutor.extract_object_ids 写入。

M2-3 实现要点：
- 仅对 category="write" 的工具启用（read 工具跳过）。
- 通过 TOOL_ID_PARAMS 配置每个写入工具参数 → 对象类型的映射。
- M3-2 写入工具上线后补充实际参数名；M2-3 先用通用规则 + 占位配置。
"""
import logging
from typing import Optional

from app.agent.types import ToolCall, SessionContext, GateResult

logger = logging.getLogger(__name__)

# 工具参数名 → 对象类型前缀映射（M3-2 写入工具上线后扩充）
# 例：update_stock 工具的 sku_id 参数 → "product" 前缀
# 规则：参数名包含某关键词则归到对应类型
TOOL_ID_PARAMS: dict = {
    # "update_stock": {"sku_id": "product", "product_id": "product"},
    # "create_order": {"customer_id": "customer"},
    # "adjust_inventory": {"sku_id": "product"},
}

# 通用参数名 → 类型前缀规则（参数名包含关键词即匹配）
PARAM_TYPE_RULES = [
    ("sku_id", "product"),
    ("product_id", "product"),
    ("order_id", "order"),
    ("customer_id", "customer"),
    ("batch_id", "product"),
]


class ProvenanceGate:
    """Provenance Gate - 来源校验

    对写入类工具，校验参数中的对象 ID 是否在本次会话 read_set 中。
    """

    async def check(self, tool_call: ToolCall, ctx: SessionContext) -> GateResult:
        """校验写入工具参数中的对象 ID 来源"""
        # 提取本次调用涉及的所有 (参数名, 对象类型, 值)
        id_refs = self._extract_id_refs(tool_call)
        if not id_refs:
            # 该工具没有对象 ID 参数，放行
            return GateResult(passed=True, reason="", gate_name="provenance")

        # 逐个校验 ID ∈ read_set
        missing = []
        for param_name, obj_type, obj_id in id_refs:
            key = f"{obj_type}:{obj_id}"
            if key not in ctx.read_set:
                missing.append((param_name, key))

        if missing:
            details = "; ".join(f"{p}={k}" for p, k in missing)
            reason = (
                f"写入操作引用了未经查询的对象 ID（{details}）。"
                f"请先调用查询工具确认该对象存在，再执行写入操作。"
            )
            logger.warning(
                f"[ProvenanceGate] 拦截工具 {tool_call.name}"
                f"（call_id={tool_call.id}）：{reason}；read_set={ctx.read_set}"
            )
            return GateResult(
                passed=False, reason=reason, gate_name="provenance",
                risk_level="high",
                metadata={"missing_ids": [k for _, k in missing]},
            )

        return GateResult(passed=True, reason="", gate_name="provenance")

    def _extract_id_refs(self, tool_call: ToolCall) -> list:
        """从工具参数中提取对象 ID 引用

        返回 [(param_name, obj_type, obj_id), ...]
        """
        refs = []
        params = tool_call.input or {}

        # 1. 工具专属配置优先
        tool_config = TOOL_ID_PARAMS.get(tool_call.name, {})
        for param_name, obj_type in tool_config.items():
            if param_name in params and params[param_name]:
                refs.append((param_name, obj_type, str(params[param_name])))

        # 2. 通用规则：参数名匹配关键词
        for param_name, value in params.items():
            if not value or param_name in tool_config:
                continue
            for keyword, obj_type in PARAM_TYPE_RULES:
                if keyword in param_name.lower():
                    refs.append((param_name, obj_type, str(value)))
                    break

        return refs
