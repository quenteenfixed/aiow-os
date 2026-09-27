"""Rate Limit Gate - 工具调用频率限制

MVP 简化版：基于内存的滑动窗口计数器。
- 每个 (agent_id, tool_name) 维护一个调用计数
- 默认限制：每分钟最多 30 次
- 进程重启后计数清零（不影响功能，仅放宽限制）

M2-3 会升级为 Redis 滑动窗口 + 配置化限制。
"""
import logging
import time
from collections import defaultdict
from typing import Dict, List, Tuple

from app.agent.types import ToolCall, SessionContext, GateResult

logger = logging.getLogger(__name__)

# 默认限制：每分钟 30 次
DEFAULT_RATE_LIMIT_PER_MINUTE = 30


class RateLimitGate:
    """Rate Limit Gate - 频率限制"""

    def __init__(self, limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE):
        self.limit_per_minute = limit_per_minute
        # key: (agent_id, tool_name), value: list of timestamps
        self._calls: Dict[Tuple[int, str], List[float]] = defaultdict(list)

    async def check(self, tool_call: ToolCall, ctx: SessionContext) -> GateResult:
        """检查 (agent_id, tool_name) 是否超频"""
        key = (ctx.agent_id, tool_call.name)
        now = time.time()
        window_start = now - 60.0  # 1 分钟窗口

        # 清理过期时间戳
        timestamps = [t for t in self._calls[key] if t > window_start]
        self._calls[key] = timestamps

        if len(timestamps) >= self.limit_per_minute:
            reason = (
                f"工具 {tool_call.name} 调用频率超限："
                f"近 1 分钟 {len(timestamps)} 次，限制 {self.limit_per_minute} 次/分钟"
            )
            logger.warning(
                f"[RateLimitGate] 拦截工具 {tool_call.name}（agent={ctx.agent_id}）：{reason}"
            )
            return GateResult(passed=False, reason=reason, gate_name="rate_limit")

        # 记录本次调用时间戳
        self._calls[key].append(now)
        return GateResult(passed=True, reason="", gate_name="rate_limit")


# 全局单例（进程级，重启后清零）
_rate_limit_instance: RateLimitGate = None


def get_rate_limit_gate() -> RateLimitGate:
    global _rate_limit_instance
    if _rate_limit_instance is None:
        _rate_limit_instance = RateLimitGate()
    return _rate_limit_instance
