"""工具调用解析器 - 从 LLM 响应中提取 tool_use 块"""
import logging
from typing import List

from app.agent.types import ToolCall
from app.agent.tools.registry import ToolRegistry, ToolNotFoundError

logger = logging.getLogger(__name__)


class ToolCallParseError(Exception):
    """工具调用解析错误"""


class ToolCallParser:
    """从 LLM 响应 content_blocks 中提取 tool_use 块"""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def parse(self, content_blocks: list, allowed_tools: List[str]) -> List[ToolCall]:
        """
        从 content_blocks 中提取 tool_use 块，校验白名单

        Args:
            content_blocks: LLM 响应的 content block 列表
            allowed_tools: 当前 Agent 允许的工具白名单
        Returns:
            校验通过的 ToolCall 列表
        """
        tool_calls = []
        for block in content_blocks:
            if block.get("type") != "tool_use":
                continue
            name = block.get("name", "")
            if not name:
                logger.warning("[Parser] tool_use 块缺少 name 字段")
                continue

            # 白名单校验
            if name not in allowed_tools:
                logger.warning(f"[Parser] 工具 {name} 不在白名单中，跳过")
                # 不抛异常，返回空 ToolCall 由上层处理为错误 tool_result
                tool_calls.append(ToolCall(
                    id=block.get("id", ""),
                    name=name,
                    input=block.get("input", {}),
                ))
                continue

            # 注册表校验
            try:
                self.registry.get(name)
            except ToolNotFoundError:
                logger.warning(f"[Parser] 工具 {name} 未在注册表中注册")
                continue

            input_data = block.get("input", {}) or {}
            if not isinstance(input_data, dict):
                logger.warning(f"[Parser] 工具 {name} input 不是 dict：{type(input_data)}")
                input_data = {}

            tool_calls.append(ToolCall(
                id=block.get("id", ""),
                name=name,
                input=input_data,
            ))

        return tool_calls

    def extract_text(self, content_blocks: list) -> str:
        """从 content_blocks 中提取文本块"""
        return "".join(
            b.get("text", "") for b in content_blocks if b.get("type") == "text"
        )
