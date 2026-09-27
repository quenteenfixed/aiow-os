"""工具注册表 - 管理工具定义、白名单、分类"""
import logging
from typing import Dict, List, Optional

from app.agent.types import ToolDefinition

logger = logging.getLogger(__name__)


class ToolNotFoundError(Exception):
    """工具不存在"""


class ToolRegistry:
    """工具注册表 - 全局唯一，进程启动时注册内置工具"""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        # 工具实现函数（handler），按 name 索引
        self._handlers: Dict[str, callable] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: dict,
        handler: callable,
        category: str = "read",
        gates: Optional[dict] = None,
    ) -> None:
        """注册工具"""
        gate_config = gates or {"fencing": True, "rate_limit": True}
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            input_schema=input_schema,
            category=category,
            gates=gate_config,
        )
        self._handlers[name] = handler
        logger.info(f"[ToolRegistry] 注册工具 {name}（{category}）")

    def get(self, name: str) -> ToolDefinition:
        if name not in self._tools:
            raise ToolNotFoundError(f"工具 {name} 未注册")
        return self._tools[name]

    def get_handler(self, name: str) -> callable:
        if name not in self._handlers:
            raise ToolNotFoundError(f"工具 {name} 的 handler 未注册")
        return self._handlers[name]

    def list_all(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def filter_by_whitelist(self, allowed: List[str]) -> List[ToolDefinition]:
        """按白名单过滤工具"""
        return [t for t in self._tools.values() if t.name in allowed]

    def is_read_tool(self, name: str) -> bool:
        """是否读取类工具"""
        if name not in self._tools:
            return False
        return self._tools[name].category == "read"

    def to_claude_format(self, tools: List[ToolDefinition]) -> list:
        """转换为 Claude API tools 参数格式"""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]


# 全局单例
_registry_instance: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册表单例（懒初始化）"""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ToolRegistry()
        # 延迟导入避免循环依赖
        from app.agent.tools.builtin import register_builtin_tools
        register_builtin_tools(_registry_instance)
        # M3-2：注册写入工具 + 配置门禁
        from app.agent.tools.write_tools import register_write_tools, configure_write_gates
        register_write_tools(_registry_instance)
        configure_write_gates()
    return _registry_instance
