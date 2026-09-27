"""工具执行器 - 调度工具实现函数，含服务端身份注入"""
import json
import logging
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.types import ToolCall, ToolResult, SessionContext
from app.agent.tools.registry import ToolRegistry, ToolNotFoundError

logger = logging.getLogger(__name__)


class ToolExecutionError(Exception):
    """工具执行异常"""


class ToolExecutor:
    """工具执行器 - 执行单个工具调用"""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(
        self,
        db: AsyncSession,
        tool_call: ToolCall,
        ctx: SessionContext,
    ) -> ToolResult:
        """
        执行单个工具调用

        关键点：
        1. 服务端身份注入：business_id 从 session 取，不信任 LLM 传入的值
        2. 捕获异常，返回 is_error=True 的 ToolResult
        3. 返回结果序列化为 JSON 字符串（方便 fencing 包裹）
        """
        start = time.time()
        try:
            handler = self.registry.get_handler(tool_call.name)
        except ToolNotFoundError:
            logger.warning(f"[ToolExecutor] 工具 {tool_call.name} 未注册")
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                content=f"工具 {tool_call.name} 未注册，无法执行。",
                is_error=True,
            )

        # 服务端身份注入：覆盖 LLM 传入的 business_id
        params = dict(tool_call.input)
        params["business_id"] = ctx.business_id
        params["db"] = db
        # 删除 LLM 可能传入的敏感字段
        params.pop("agent_id", None)

        try:
            result_data = await handler(**params)
            elapsed_ms = int((time.time() - start) * 1000)

            # 序列化结果
            if isinstance(result_data, (dict, list)):
                content = json.dumps(result_data, ensure_ascii=False, default=str)
            else:
                content = str(result_data)

            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                content=content,
                is_error=False,
                metadata={"execution_time_ms": elapsed_ms},
            )
        except Exception as e:
            logger.error(f"[ToolExecutor] 工具 {tool_call.name} 执行失败：{e}", exc_info=True)
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                content=f"工具执行失败：{type(e).__name__}: {str(e)}",
                is_error=True,
                metadata={"execution_time_ms": int((time.time() - start) * 1000)},
            )

    def extract_object_ids(self, tool_name: str, result: ToolResult) -> set:
        """从工具结果中提取对象 ID（供 Provenance Gate 用，M2-3 启用）"""
        ids = set()
        try:
            data = json.loads(result.content) if isinstance(result.content, str) else result.content
            if isinstance(data, dict):
                items = data.get("items", [])
                if isinstance(items, list):
                    for it in items:
                        if isinstance(it, dict):
                            obj_id = it.get("id") or it.get("sku_id") or it.get("product_id")
                            if obj_id:
                                prefix = "product" if "product" in tool_name or "sku" in tool_name else "order"
                                ids.add(f"{prefix}:{obj_id}")
        except (json.JSONDecodeError, TypeError):
            pass
        return ids
