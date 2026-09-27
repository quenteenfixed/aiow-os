"""Guardrail Gate - 参数护栏，防危险参数

对工具参数做范围与格式校验，拦截：
1. 分页参数越界（page < 1, page_size > 20）
2. 数值异常（负数、过大金额、过大数量）
3. SQL 注入特征字符串（UNION SELECT / DROP / ; -- 等）
4. 字符串长度超限（防止超长输入导致 LLM 注入或 DB 压力）
5. 任意 code 执行特征（__import__ / eval / exec / os.system）

M2-3 为 read 工具（分页/关键词）和未来 write 工具（数量/金额）都做护栏。
配置驱动：TOOL_GUARDRAILS 字典为每个工具定义参数约束。
"""
import logging
import re
from typing import Optional

from app.agent.types import ToolCall, SessionContext, GateResult

logger = logging.getLogger(__name__)

# 通用护栏：适用于所有工具的参数约束
COMMON_GUARDRAILS = {
    "page": {"min": 1, "max": 1000, "type": "int"},
    "page_size": {"min": 1, "max": 20, "type": "int"},
    "keyword": {"max_len": 200, "type": "str"},
    "category": {"max_len": 100, "type": "str"},
    "brand": {"max_len": 100, "type": "str"},
    "sku_code": {"max_len": 100, "type": "str"},
}

# 工具专属护栏（M3-2 写入工具上线后扩充）
TOOL_GUARDRAILS: dict = {
    # "update_stock": {
    #     "quantity": {"min": 0, "max": 100000, "type": "int"},
    #     "reason": {"max_len": 500, "type": "str"},
    # },
    # "create_order": {
    #     "total_amount": {"min": 0, "max": 10000000, "type": "float"},
    # },
}

# SQL 注入特征（大小写不敏感）
SQL_INJECTION_PATTERNS = [
    r"\bunion\s+select\b",
    r"\bselect\b.*\bfrom\b.*\b--",
    r"\bdrop\s+(table|database)\b",
    r"\bdelete\s+from\b",
    r"\binsert\s+into\b",
    r"\bupdate\b.*\bset\b.*\bwhere\b",
    r"'\s*or\s*'1'\s*=\s*'1",
    r"'\s*or\s*1\s*=\s*1",
    r"--\s*$",
    r";\s*(drop|delete|update|insert)\b",
]

# 代码执行特征（防 LLM 试图通过参数触发 Python 代码执行）
CODE_EXEC_PATTERNS = [
    r"__import__\s*\(",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\bos\.(system|popen)\s*\(",
    r"\bsubprocess\.",
    r"\bopen\s*\(",
]

_COMPILED_SQL = [re.compile(p, re.IGNORECASE) for p in SQL_INJECTION_PATTERNS]
_COMPILED_CODE = [re.compile(p, re.IGNORECASE) for p in CODE_EXEC_PATTERNS]


class GuardrailGate:
    """Guardrail Gate - 参数护栏"""

    async def check(self, tool_call: ToolCall, ctx: SessionContext) -> GateResult:
        """校验工具参数范围与格式"""
        params = tool_call.input or {}

        # 合并通用护栏 + 工具专属护栏
        rules = dict(COMMON_GUARDRAILS)
        rules.update(TOOL_GUARDRAILS.get(tool_call.name, {}))

        # 1. 数值范围校验
        for param_name, value in params.items():
            rule = rules.get(param_name)
            if rule is None:
                continue
            if "type" in rule and rule["type"] in ("int", "float"):
                num_result = self._check_number(param_name, value, rule)
                if num_result is not None:
                    return num_result
            elif "type" in rule and rule["type"] == "str":
                str_result = self._check_string(param_name, value, rule)
                if str_result is not None:
                    return str_result

        # 2. SQL 注入检测（对所有字符串参数）
        for param_name, value in params.items():
            if not isinstance(value, str):
                continue
            for pattern in _COMPILED_SQL:
                if pattern.search(value):
                    reason = (
                        f"参数 {param_name} 包含可疑 SQL 注入特征：{pattern.pattern}。"
                        f"请使用正常的查询关键词。"
                    )
                    logger.warning(
                        f"[GuardrailGate] 拦截工具 {tool_call.name}"
                        f"（call_id={tool_call.id}）：{reason}"
                    )
                    return GateResult(
                        passed=False, reason=reason, gate_name="guardrail",
                        risk_level="high", metadata={"param": param_name},
                    )

            # 3. 代码执行特征检测
            for pattern in _COMPILED_CODE:
                if pattern.search(value):
                    reason = (
                        f"参数 {param_name} 包含可疑代码执行特征：{pattern.pattern}。"
                        f"禁止在参数中包含可执行代码。"
                    )
                    logger.warning(
                        f"[GuardrailGate] 拦截工具 {tool_call.name}"
                        f"（call_id={tool_call.id}）：{reason}"
                    )
                    return GateResult(
                        passed=False, reason=reason, gate_name="guardrail",
                        risk_level="high", metadata={"param": param_name},
                    )

        return GateResult(passed=True, reason="", gate_name="guardrail")

    def _check_number(self, param_name: str, value, rule: dict) -> Optional[GateResult]:
        """数值范围校验"""
        try:
            num = float(value)
        except (TypeError, ValueError):
            reason = f"参数 {param_name} 应为数值，实际为 {type(value).__name__}。"
            logger.warning(f"[GuardrailGate] {reason}")
            return GateResult(
                passed=False, reason=reason, gate_name="guardrail",
                risk_level="medium", metadata={"param": param_name},
            )

        if "min" in rule and num < rule["min"]:
            reason = f"参数 {param_name}={num} 小于最小值 {rule['min']}。"
            logger.warning(f"[GuardrailGate] {reason}")
            return GateResult(
                passed=False, reason=reason, gate_name="guardrail",
                risk_level="medium", metadata={"param": param_name},
            )

        if "max" in rule and num > rule["max"]:
            reason = f"参数 {param_name}={num} 超过最大值 {rule['max']}。"
            logger.warning(f"[GuardrailGate] {reason}")
            return GateResult(
                passed=False, reason=reason, gate_name="guardrail",
                risk_level="medium", metadata={"param": param_name},
            )

        return None

    def _check_string(self, param_name: str, value, rule: dict) -> Optional[GateResult]:
        """字符串长度校验"""
        if not isinstance(value, str):
            value = str(value)

        if "max_len" in rule and len(value) > rule["max_len"]:
            reason = (
                f"参数 {param_name} 长度 {len(value)} 超过上限 {rule['max_len']}。"
                f"请精简输入。"
            )
            logger.warning(f"[GuardrailGate] {reason}")
            return GateResult(
                passed=False, reason=reason, gate_name="guardrail",
                risk_level="low", metadata={"param": param_name},
            )

        return None
