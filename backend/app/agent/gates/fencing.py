"""Fencing Gate - 检查工具参数中是否包含伪造的围栏标记

防止 LLM 通过工具参数注入系统级指令（prompt injection 防御）。
扫描工具 input 的所有字符串值，发现可疑标记则拦截。
"""
import json
import logging
import re

from app.agent.types import ToolCall, SessionContext, GateResult

logger = logging.getLogger(__name__)

# 围栏标记黑名单 - 出现在工具参数中即视为伪造
FENCING_PATTERNS = [
    r"<\s*fenced\s*>",
    r"<\s*/\s*fenced\s*>",
    r"<\s*system\s*>",
    r"<\s*/\s*system\s*>",
    r"<\s*assistant\s*>",
    r"<\s*/\s*assistant\s*>",
    r"<\s*tool_result\s*>",
    r"<\s*/\s*tool_result\s*>",
    r"<\s*tool_use\s*>",
    r"<\s*/\s*tool_use\s*>",
    r"#\s*fencing",
    r"#\s*围栏",
    r"<\|system\|>",
    r"<\|assistant\|>",
    r"<\|end\|>",
    r"忽略.*之前.*指令",
    r"ignore.*previous.*instructions",
    r"你现在是",
    r"重新设定.*角色",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in FENCING_PATTERNS]


class FencingGate:
    """Fencing Gate - 围栏标记检测"""

    async def check(self, tool_call: ToolCall, ctx: SessionContext) -> GateResult:
        """检查工具 input 中是否包含伪造的围栏标记"""
        try:
            input_str = json.dumps(tool_call.input, ensure_ascii=False)
        except (TypeError, ValueError):
            input_str = str(tool_call.input)

        for pattern in _COMPILED_PATTERNS:
            if pattern.search(input_str):
                reason = f"工具参数中检测到可疑围栏标记：{pattern.pattern}"
                logger.warning(
                    f"[FencingGate] 拦截工具 {tool_call.name}（call_id={tool_call.id}）：{reason}"
                )
                return GateResult(passed=False, reason=reason, gate_name="fencing")

        return GateResult(passed=True, reason="", gate_name="fencing")
