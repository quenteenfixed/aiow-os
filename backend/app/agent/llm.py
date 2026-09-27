"""LLM 客户端 - 抽象基类 + MockLLMClient（无 key 自动降级）+ AnthropicLLMClient（真实）

设计要点：
1. 无 API key 时自动降级到 MockLLMClient，可识别常见查询意图并模拟 tool_use
2. 有 ANTHROPIC_API_KEY 时使用真实 Claude API
3. 统一返回 LLMResponse（content_blocks + usage + latency_ms）
4. 支持流式与非流式（MVP 阶段 Mock 用非流式，真实 API 用流式）
"""
import json
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import json

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """LLM 响应统一结构"""
    content_blocks: list  # [{"type": "text", "text": "..."} / {"type": "tool_use", "id": "...", "name": "...", "input": {...}}]
    usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})
    latency_ms: int = 0
    stop_reason: Optional[str] = None


class LLMError(Exception):
    """LLM 调用异常"""


class LLMClient:
    """LLM 客户端抽象基类"""

    async def messages_create(
        self,
        model: str,
        max_tokens: int,
        temperature: float,
        system: str,
        messages: list,
        tools: Optional[list] = None,
        stream: bool = False,
    ) -> LLMResponse:
        raise NotImplementedError


# ===== MockLLMClient - 无 key 时自动降级 =====

class MockLLMClient(LLMClient):
    """Mock LLM 客户端 - 不调用真实 API，基于规则模拟 tool_use

    识别常见查询意图：
    - "可口可乐库存" / "xxx 库存" / "库存多少" → search_products({keyword: "xxx"})
    - "订单详情" / "订单 xxx" → list_orders({order_no: "xxx"})
    - 已经有工具结果时，基于结果生成自然语言回复
    """

    def __init__(self):
        self._call_count = 0

    async def messages_create(
        self,
        model: str,
        max_tokens: int,
        temperature: float,
        system: str,
        messages: list,
        tools: Optional[list] = None,
        stream: bool = False,
    ) -> LLMResponse:
        start = time.time()
        self._call_count += 1
        # 取最后一条用户消息文本
        last_user_text = self._extract_last_user_text(messages)
        # 检查上一条是否是 tool_result（如果是，则基于结果回复）
        has_tool_result = self._last_message_has_tool_result(messages)

        if has_tool_result:
            tool_result_text = self._extract_last_tool_result_content(messages)
            # M3-2：如果是 pending_approval 结果，直接回复"已提交审批"
            if "已提交审批" in tool_result_text or "pending_approval" in tool_result_text:
                reply = "该操作已提交审批，等待店主确认后执行。你可以在工单列表中查看审批进度。"
                return LLMResponse(
                    content_blocks=[{"type": "text", "text": reply}],
                    usage={"input_tokens": 200, "output_tokens": len(reply) // 4 + 10},
                    latency_ms=int((time.time() - start) * 1000),
                    stop_reason="end_turn",
                )
            # M3-2：检查是否有写入意图（用户原始消息含调价/入库/退款等关键词）
            # 且当前 tool_result 是查询结果（不是 pending_approval）
            # 如果是，则调用写入工具（而非生成文本回复）
            messages_text = self._messages_to_text(messages)
            tool_names = {t.get("name") for t in (tools or [])}
            write_intent = self._detect_write_intent(last_user_text, messages_text, tool_names)
            if write_intent:
                return LLMResponse(
                    content_blocks=[
                        {"type": "text", "text": f"好的，我来执行{write_intent['_intent_label']}。"},
                        {"type": "tool_use", "id": write_intent["id"], "name": write_intent["name"], "input": write_intent["input"]},
                    ],
                    usage={"input_tokens": 200, "output_tokens": 60},
                    latency_ms=int((time.time() - start) * 1000),
                    stop_reason="tool_use",
                )
            # 基于工具结果生成自然语言回复
            reply = self._summarize_tool_result(tool_result_text)
            return LLMResponse(
                content_blocks=[{"type": "text", "text": reply}],
                usage={"input_tokens": 200, "output_tokens": len(reply) // 4 + 10},
                latency_ms=int((time.time() - start) * 1000),
                stop_reason="end_turn",
            )

        # 首次输入，识别意图并模拟 tool_use
        messages_text = self._messages_to_text(messages)
        tool_call = self._detect_intent(last_user_text, tools or [], messages_text)
        if tool_call:
            return LLMResponse(
                content_blocks=[
                    {"type": "text", "text": f"好的，我来查询一下{tool_call['_intent_label']}。"},
                    {"type": "tool_use", "id": tool_call["id"], "name": tool_call["name"], "input": tool_call["input"]},
                ],
                usage={"input_tokens": 150, "output_tokens": 50},
                latency_ms=int((time.time() - start) * 1000),
                stop_reason="tool_use",
            )

        # 无工具调用意图，直接回复
        reply = f"我理解你说的是：{last_user_text}。作为门店管家，我可以帮你查询商品、库存、订单等信息。请告诉我具体想了解什么？"
        return LLMResponse(
            content_blocks=[{"type": "text", "text": reply}],
            usage={"input_tokens": 100, "output_tokens": len(reply) // 4 + 10},
            latency_ms=int((time.time() - start) * 1000),
            stop_reason="end_turn",
        )

    def _extract_last_user_text(self, messages: list) -> str:
        """从 messages 中取最后一条 role=user 且 content 为字符串的消息文本"""
        for msg in reversed(messages):
            if msg.get("role") != "user":
                continue
            content = msg.get("content")
            if isinstance(content, str):
                return content
            # content 是 list（含 tool_result）则跳过，继续找更早的纯文本消息
            if isinstance(content, list):
                # 取 list 中 type=text 的块文本
                texts = [b.get("text", "") for b in content if b.get("type") == "text"]
                if texts:
                    return "\n".join(texts)
        return ""

    def _last_message_has_tool_result(self, messages: list) -> bool:
        """判断最后一条消息是否包含 tool_result 块"""
        if not messages:
            return False
        last = messages[-1]
        content = last.get("content")
        if isinstance(content, list):
            return any(b.get("type") == "tool_result" for b in content)
        return False

    def _extract_last_tool_result_content(self, messages: list) -> str:
        """提取最后一条 tool_result 块的内容文本"""
        last = messages[-1]
        content = last.get("content", [])
        if isinstance(content, list):
            for b in content:
                if b.get("type") == "tool_result":
                    c = b.get("content", "")
                    if isinstance(c, str):
                        return c
                    return json.dumps(c, ensure_ascii=False)
        return ""

    def _detect_intent(self, text: str, tools: list, messages_text: str = "") -> Optional[dict]:
        """识别查询意图，返回 tool_use 模拟响应"""
        if not text:
            return None
        text_lower = text.lower()
        # 提取工具名集合
        tool_names = {t.get("name") for t in tools} if isinstance(tools, list) else set()

        # 1. 经营概览（优先级最高，关键词最特异）
        overview_kws = ["经营概览", "生意怎么样", "今天怎么样", "概况", "总体情况", "经营情况", "整体情况", "概览"]
        if any(k in text for k in overview_kws):
            if "business_overview" in tool_names:
                # 根据关键词推断 period
                period = "today" if "今天" in text else "7d"
                return {
                    "id": f"tool_{self._call_count}_1",
                    "name": "business_overview",
                    "input": {"period": period},
                    "_intent_label": "经营概览",
                }

        # 2. 销售统计
        sales_kws = ["销售统计", "营业额", "销售额", "今天卖了", "卖了多", "订单统计", "成交额", "交易额"]
        if any(k in text for k in sales_kws):
            if "sales_stats" in tool_names:
                period = "today" if "今天" in text else ("30d" if ("30天" in text or "月" in text) else "7d")
                return {
                    "id": f"tool_{self._call_count}_1",
                    "name": "sales_stats",
                    "input": {"period": period},
                    "_intent_label": "销售统计",
                }

        # 3. 临期商品
        expiring_kws = ["临期", "快过期", "快到期", "过期", "到期", "保质期"]
        if any(k in text for k in expiring_kws):
            if "check_expiring" in tool_names:
                # 提取天数（如"30天内"）
                days = 30
                import re as _re
                m = _re.search(r"(\d+)\s*天", text)
                if m:
                    days = int(m.group(1))
                return {
                    "id": f"tool_{self._call_count}_1",
                    "name": "check_expiring",
                    "input": {"days": days},
                    "_intent_label": "临期商品",
                }

        # 4. 库存流水
        history_kws = ["流水", "入库记录", "出库记录", "库存记录", "库存变化", "库存变动", "出入库"]
        if any(k in text for k in history_kws):
            if "inventory_history" in tool_names:
                return {
                    "id": f"tool_{self._call_count}_1",
                    "name": "inventory_history",
                    "input": {},
                    "_intent_label": "库存流水",
                }

        # 5. 库存/商品查询：包含"库存""商品""xxx 库存多少""xxx 还有几个"
        if "库存" in text or "存货" in text or "还有多少" in text or "剩多少" in text:
            if "search_products" in tool_names:
                # 提取关键词：去掉"库存""多少""还有""剩"等词
                keyword = text
                for w in ["的库存", "库存", "的存货", "存货", "还有多少", "剩多少", "多少", "还有", "剩", "查询", "查一下", "帮我", "请问", "？", "?"]:
                    keyword = keyword.replace(w, "")
                keyword = keyword.strip() or "商品"
                return {
                    "id": f"tool_{self._call_count}_1",
                    "name": "search_products",
                    "input": {"keyword": keyword},
                    "_intent_label": f"{keyword} 的库存",
                }

        # 6. 订单查询
        if "订单" in text or "单号" in text or "成交" in text:
            if "list_orders" in tool_names:
                return {
                    "id": f"tool_{self._call_count}_1",
                    "name": "list_orders",
                    "input": {},
                    "_intent_label": "订单列表",
                }

        # 7. 写入工具意图（M3-2）— 两步流程：先查询 ID，再调用写入工具
        write_result = self._detect_write_intent(text, messages_text, tool_names)
        if write_result:
            return write_result

        return None

    def _messages_to_text(self, messages: list) -> str:
        """将消息列表转为纯文本（供正则提取用）"""
        parts = []
        for msg in messages:
            role = msg.get("role", "")
            c = msg.get("content", "")
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, list):
                for block in c:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_result":
                            parts.append(str(block.get("content", "")))
                        elif block.get("type") == "tool_use":
                            parts.append(json.dumps(block.get("input", {}), ensure_ascii=False))
        return " ".join(parts)

    def _detect_write_intent(self, text: str, messages_text: str, tool_names: set) -> Optional[dict]:
        """检测写入工具意图（M3-2）

        两步流程：
        1. 如果用户消息含写入关键词但尚未查询 ID → 先调用查询工具
        2. 如果已查询到 ID → 调用写入工具
        """
        import re, json as _json

        # 提取已查询到的对象 ID（从 messages_text 中搜索 tool_result）
        queried_ids = {}
        # 搜索 JSON 中的 "id" 字段（UUID 格式）
        uuid_pattern = r'"id"\s*:\s*"(?[0-9a-f-]{36})'
        uuids = re.findall(r'"id"\s*:\s*"([0-9a-f-]{36})"', messages_text)
        if uuids:
            queried_ids["sku_id"] = uuids[0]
            queried_ids["order_id"] = uuids[0]

        # 7a. 价格调整
        price_kws = ["调价", "改价", "调整价格", "价格调整", "改一下价格", "改成", "调到"]
        if any(k in text for k in price_kws) and "adjust_price" in tool_names:
            # 提取目标价格
            price_match = re.search(r"(\d+\.?\d*)\s*元?", text)
            new_price = float(price_match.group(1)) if price_match else 4.0

            if "sku_id" in queried_ids:
                # 已查询到 SKU ID，调用写入工具
                return {
                    "id": f"tool_{self._call_count}_1",
                    "name": "adjust_price",
                    "input": {
                        "sku_id": queried_ids["sku_id"],
                        "new_price": new_price,
                        "reason": "用户要求调价",
                    },
                    "_intent_label": f"调价到 {new_price} 元",
                }
            else:
                # 先查询商品（提取关键词）
                keyword = text
                for w in ["调价", "改价", "调整价格", "价格调整", "的价格", "价格", "改成", "调到", "元", "帮我把", "帮我", "请问", "多少"]:
                    keyword = keyword.replace(w, "")
                # 提取价格数字前部分作为商品名
                price_split = re.split(r"\d+\.?\d*\s*元?", keyword)
                keyword = price_split[0].strip() or "商品"
                if "search_products" in tool_names:
                    return {
                        "id": f"tool_{self._call_count}_1",
                        "name": "search_products",
                        "input": {"keyword": keyword},
                        "_intent_label": f"查询 {keyword}（为调价准备）",
                    }

        # 7b. 库存调整（入库/出库）
        stock_kws = ["入库", "进货", "出库", "出货", "盘点", "补货"]
        if any(k in text for k in stock_kws) and "adjust_stock" in tool_names:
            qty_match = re.search(r"(\d+)\s*(件|个|瓶|箱|包)", text)
            qty = int(qty_match.group(1)) if qty_match else 10
            change_type = "out" if ("出库" in text or "出货" in text) else "in"

            if "sku_id" in queried_ids:
                return {
                    "id": f"tool_{self._call_count}_1",
                    "name": "adjust_stock",
                    "input": {
                        "sku_id": queried_ids["sku_id"],
                        "change_type": change_type,
                        "change_qty": qty if change_type == "in" else -qty,
                        "reason": f"用户要求{change_type}",
                    },
                    "_intent_label": f"{change_type} {qty} 件",
                }
            else:
                keyword = text
                for w in ["入库", "进货", "出库", "出货", "盘点", "补货", "帮我把", "帮我", "请问", "的库存", "库存"]:
                    keyword = keyword.replace(w, "")
                qty_split = re.split(r"\d+\s*(件|个|瓶|箱|包)", keyword)
                keyword = qty_split[0].strip() or "商品"
                if "search_products" in tool_names:
                    return {
                        "id": f"tool_{self._call_count}_1",
                        "name": "search_products",
                        "input": {"keyword": keyword},
                        "_intent_label": f"查询 {keyword}（为{change_type}准备）",
                    }

        # 7c. 退款
        refund_kws = ["退款", "退货退款", "退单"]
        if any(k in text for k in refund_kws) and "process_refund" in tool_names:
            amount_match = re.search(r"(\d+\.?\d*)\s*元?", text)
            refund_amount = float(amount_match.group(1)) if amount_match else 0

            if "order_id" in queried_ids:
                return {
                    "id": f"tool_{self._call_count}_1",
                    "name": "process_refund",
                    "input": {
                        "order_id": queried_ids["order_id"],
                        "refund_amount": refund_amount,
                        "refund_reason": "用户要求退款",
                        "refund_type": "full" if refund_amount == 0 else "partial",
                    },
                    "_intent_label": f"退款 {refund_amount} 元",
                }
            else:
                if "list_orders" in tool_names:
                    return {
                        "id": f"tool_{self._call_count}_1",
                        "name": "list_orders",
                        "input": {},
                        "_intent_label": "查询订单（为退款准备）",
                    }

        # 7d. 采购建议
        purchase_kws = ["采购建议", "进货建议", "补货建议", "该进什么货"]
        if any(k in text for k in purchase_kws) and "suggest_purchase" in tool_names:
            return {
                "id": f"tool_{self._call_count}_1",
                "name": "suggest_purchase",
                "input": {"reason": "基于库存分析生成采购建议"},
                "_intent_label": "采购建议",
            }

        return None

    def _summarize_tool_result(self, tool_result_text: str) -> str:
        """基于工具结果生成自然语言回复"""
        # 尝试解析 JSON
        try:
            data = json.loads(tool_result_text) if tool_result_text.strip().startswith("{") else None
        except (json.JSONDecodeError, AttributeError):
            data = None

        if isinstance(data, dict):
            # === 经营概览（business_overview）：无 items，按 nested 字段汇总 ===
            if "product" in data and "inventory" in data and "orders" in data:
                prod = data.get("product", {})
                inv = data.get("inventory", {})
                ords = data.get("orders", {})
                cust = data.get("customers", {})
                lvl = cust.get("level_distribution", {})
                lines = [
                    f"经营概览（周期：{data.get('period', '-')}）：",
                    f"  • 商品：{prod.get('product_count', 0)} 个 SPU / {prod.get('sku_count', 0)} 个 SKU",
                    f"  • 库存：总值 ¥{inv.get('stock_total_value', 0)}，缺货 {inv.get('out_of_stock_count', 0)} 个，低库存 {inv.get('low_stock_count', 0)} 个",
                    f"  • 订单：{ords.get('total_orders', 0)} 单，销售额 ¥{ords.get('total_amount', 0)}，客单价 ¥{ords.get('avg_order_value', 0)}（已完成 {ords.get('completed_count', 0)} / 取消 {ords.get('cancelled_count', 0)} / 退款 {ords.get('refunded_count', 0)}）",
                    f"  • 客户：共 {cust.get('total_customers', 0)} 位（普通 {lvl.get('normal', 0)} / VIP {lvl.get('vip', 0)} / SVIP {lvl.get('svip', 0)}）",
                ]
                return "\n".join(lines)

            # === 销售统计（sales_stats）：summary 字段 ===
            if "summary" in data and "period" in data and "items" not in data:
                sm = data.get("summary", {})
                lines = [
                    f"销售统计（周期：{data.get('period', '-')}）：",
                    f"  • 订单总数：{sm.get('total_orders', 0)} 单",
                    f"  • 销售额：¥{sm.get('total_amount', 0)}",
                    f"  • 客单价：¥{sm.get('avg_order_value', 0)}",
                    f"  • 已完成 {sm.get('completed_count', 0)} / 取消 {sm.get('cancelled_count', 0)} / 退款 {sm.get('refunded_count', 0)}",
                ]
                return "\n".join(lines)

            items = data.get("items") or data.get("data", {}).get("items") or []
            total = data.get("total", len(items))

            # === 临期商品（check_expiring）：items 含 batch_no/expire_date/days_remaining ===
            if items and isinstance(items[0], dict) and "batch_no" in items[0]:
                lines = [f"临期商品（{data.get('days_threshold', 30)} 天内将到期，共 {total} 条）："]
                for it in items[:10]:
                    name = it.get("product_name") or it.get("sku_code") or "商品"
                    days_left = it.get("days_remaining")
                    expire = it.get("expire_date", "")
                    batch = it.get("batch_no", "")
                    qty = it.get("remaining_qty", 0)
                    days_str = f"剩 {days_left} 天" if days_left is not None else "未知"
                    lines.append(f"  • {name}（批次 {batch}）：剩余 {qty} 件，到期日 {expire}（{days_str}）")
                if total > len(items):
                    lines.append(f"  ... 还有 {total - len(items)} 条未显示")
                return "\n".join(lines)

            # === 库存流水（inventory_history）：items 含 change_type/change_qty ===
            if items and isinstance(items[0], dict) and "change_type" in items[0] and "batch_no" not in items[0]:
                type_map = {"in": "入库", "out": "出库", "adjust": "调整", "check": "盘点", "return": "退货"}
                lines = [f"库存流水（共 {total} 条）："]
                for it in items[:10]:
                    name = it.get("product_name") or it.get("sku_code") or "SKU"
                    ct = type_map.get(it.get("change_type"), it.get("change_type", ""))
                    cq = it.get("change_qty", 0)
                    aq = it.get("after_qty", 0)
                    reason = it.get("reason", "")
                    t = it.get("created_at", "")
                    lines.append(f"  • {t} {name}：{ct} {cq}（余 {aq}）{reason}")
                if total > len(items):
                    lines.append(f"  ... 还有 {total - len(items)} 条未显示")
                return "\n".join(lines)

            # === 客户详情（get_customer）：含 total_orders/total_amount/level ===
            if "level" in data and "total_orders" in data and "items" not in data:
                lines = [
                    f"客户档案：{data.get('name', '-')}（{data.get('phone', '-')}）",
                    f"  • 等级：{data.get('level', '-')}",
                    f"  • 累计消费：{data.get('total_orders', 0)} 单 / ¥{data.get('total_amount', 0)}",
                    f"  • 标签：{', '.join(data.get('tags') or []) or '无'}",
                ]
                orders = data.get("orders") or []
                if orders:
                    lines.append(f"  • 最近 {len(orders)} 笔订单：")
                    for o in orders[:5]:
                        lines.append(f"    - {o.get('order_no', '')}：{o.get('status', '')} ¥{o.get('total_amount', 0)}（{o.get('created_at', '')}）")
                return "\n".join(lines)

            # === 商品详情（get_product）：含 skus 列表 ===
            if "skus" in data and "name" in data and "items" not in data:
                lines = [f"商品详情：{data.get('name', '-')}（分类 {data.get('category', '-')}/品牌 {data.get('brand', '-')}）"]
                skus = data.get("skus") or []
                lines.append(f"  • 共 {len(skus)} 个 SKU，总库存 {data.get('total_stock', 0)} 件：")
                for sk in skus[:10]:
                    lines.append(f"    - {sk.get('sku_code', '')}（{sk.get('spec_name', '')}）：¥{sk.get('price', 0)} 库存 {sk.get('stock_qty', 0)}")
                return "\n".join(lines)

            # === 通用列表场景 ===
            if items:
                # 商品/库存场景
                first = items[0]
                if "stock_qty" in first:
                    lines = []
                    for it in items[:5]:
                        name = it.get("product_name") or it.get("sku_code") or "商品"
                        qty = it.get("stock_qty", 0)
                        status = it.get("stock_status", "")
                        lines.append(f"  • {name}：库存 {qty} 件（{status}）")
                    return "查询结果如下：\n" + "\n".join(lines) + (f"\n\n共 {total} 条记录。" if total > len(items) else "")
                # 订单场景
                if "order_no" in first:
                    lines = []
                    for it in items[:5]:
                        lines.append(f"  • 单号 {it.get('order_no')}：{it.get('customer_name')} 金额 {it.get('total_amount')} 状态 {it.get('status')}")
                    return "查询到订单：\n" + "\n".join(lines) + (f"\n\n共 {total} 条记录。" if total > len(items) else "")
            return f"查询完成，共返回 {total} 条记录。"

        # === M3-2：写入工具审批结果 ===
        if "已提交审批" in tool_result_text or "pending_approval" in tool_result_text:
            return "该操作已提交审批，等待店主确认后执行。你可以在工单列表中查看审批进度。"

        # 非结构化结果，直接截断返回
        snippet = tool_result_text[:300]
        return f"查询结果：{snippet}"

    def _extract_text(self, content_blocks: list) -> str:
        return "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")


# ===== AnthropicLLMClient - 真实 API =====

class AnthropicLLMClient(LLMClient):
    """真实 Anthropic Claude API 客户端 - 有 API key 时启用"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        # 延迟导入，避免无 key 时报错
        try:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=api_key)
        except ImportError:
            raise LLMError("anthropic 包未安装，请运行 pip install anthropic")

    async def messages_create(
        self,
        model: str,
        max_tokens: int,
        temperature: float,
        system: str,
        messages: list,
        tools: Optional[list] = None,
        stream: bool = False,
    ) -> LLMResponse:
        start = time.time()
        try:
            kwargs = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system,
                "messages": messages,
            }
            if tools:
                kwargs["tools"] = tools

            if stream:
                # 流式收集
                collected_text = ""
                collected_tool_use = []
                usage_input = usage_output = 0
                async with self._client.messages.stream(**kwargs) as s:
                    async for evt in s:
                        if evt.type == "content_block_delta":
                            if evt.delta.type == "text_delta":
                                collected_text += evt.delta.text
                        elif evt.type == "message_delta":
                            if hasattr(evt, "usage") and evt.usage:
                                usage_output = getattr(evt.usage, "output_tokens", usage_output)
                    final = await s.get_final_message()
                    content_blocks = []
                    if collected_text:
                        content_blocks.append({"type": "text", "text": collected_text})
                    for b in final.content:
                        if b.type == "tool_use":
                            content_blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
                    usage_input = final.usage.input_tokens if final.usage else usage_input
                    usage_output = usage_output or (final.usage.output_tokens if final.usage else 0)
                    return LLMResponse(
                        content_blocks=content_blocks,
                        usage={"input_tokens": usage_input, "output_tokens": usage_output},
                        latency_ms=int((time.time() - start) * 1000),
                        stop_reason=final.stop_reason,
                    )
            else:
                resp = await self._client.messages.create(**kwargs)
                content_blocks = []
                for b in resp.content:
                    if b.type == "text":
                        content_blocks.append({"type": "text", "text": b.text})
                    elif b.type == "tool_use":
                        content_blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
                return LLMResponse(
                    content_blocks=content_blocks,
                    usage={"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens},
                    latency_ms=int((time.time() - start) * 1000),
                    stop_reason=resp.stop_reason,
                )
        except Exception as e:
            logger.error(f"[AnthropicLLM] API 调用失败：{e}")
            raise LLMError(str(e))



# ===== DeepSeekLLMClient - OpenAI 兼容协议（DeepSeek）=====

class DeepSeekLLMClient(LLMClient):
    """DeepSeek LLM 客户端 - 通过 OpenAI 兼容协议调用

    负责在 Anthropic 消息/工具格式 与 OpenAI 格式之间做双向转换：
    - 入参：Claude 格式 messages（含 tool_use/tool_result content blocks）+ tools
    - 出参：LLMResponse（content_blocks 含 text/tool_use，与 Anthropic 客户端一致）
    """

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._base_url = base_url

    # ---------- 格式转换：Claude → OpenAI ----------

    @staticmethod
    def _convert_tools(claude_tools: list) -> list:
        """Claude 工具定义 → OpenAI 工具定义"""
        openai_tools = []
        for t in claude_tools or []:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                },
            })
        return openai_tools

    @staticmethod
    def _convert_messages(claude_messages: list, system: str) -> list:
        """Claude 消息列表 → OpenAI 消息列表

        关键点：
        - system 作为首条 role=system 消息
        - Claude 的 tool_result（role=user，content 是 tool_result 块）
          → OpenAI 的 role=tool 消息（每个 tool_result 单独一条）
        - Claude 的 assistant tool_use 块 → OpenAI 的 tool_calls
        """
        openai_messages = []
        if system:
            openai_messages.append({"role": "system", "content": system})

        for msg in claude_messages:
            role = msg.get("role")
            content = msg.get("content")

            if role == "user":
                # content 可能是字符串或 content blocks 列表
                if isinstance(content, str):
                    openai_messages.append({"role": "user", "content": content})
                elif isinstance(content, list):
                    # 检查是否全是 tool_result
                    tool_results = [b for b in content if b.get("type") == "tool_result"]
                    if tool_results:
                        for tr in tool_results:
                            openai_messages.append({
                                "role": "tool",
                                "tool_call_id": tr.get("tool_use_id", ""),
                                "content": tr.get("content", ""),
                            })
                    else:
                        # 普通文本块拼接
                        text_parts = [b.get("text", "") for b in content if b.get("type") == "text"]
                        if text_parts:
                            openai_messages.append({"role": "user", "content": "\n".join(text_parts)})
                else:
                    openai_messages.append({"role": "user", "content": str(content or "")})

            elif role == "assistant":
                if isinstance(content, str):
                    openai_messages.append({"role": "assistant", "content": content})
                elif isinstance(content, list):
                    text_parts = [b.get("text", "") for b in content if b.get("type") == "text"]
                    tool_uses = [b for b in content if b.get("type") == "tool_use"]
                    assistant_msg = {
                        "role": "assistant",
                        "content": "\n".join(text_parts) if text_parts else None,
                    }
                    if tool_uses:
                        assistant_msg["tool_calls"] = [
                            {
                                "id": tu.get("id", ""),
                                "type": "function",
                                "function": {
                                    "name": tu.get("name", ""),
                                    "arguments": json.dumps(tu.get("input", {}), ensure_ascii=False),
                                },
                            }
                            for tu in tool_uses
                        ]
                    openai_messages.append(assistant_msg)
            elif role == "tool":
                # 兜底：直接透传
                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id", ""),
                    "content": content if isinstance(content, str) else str(content),
                })

        return openai_messages

    # ---------- 格式转换：OpenAI → LLMResponse ----------

    @staticmethod
    def _convert_response(resp) -> LLMResponse:
        """OpenAI ChatCompletion → LLMResponse（Claude content_blocks 格式）"""
        msg = resp.choices[0].message
        content_blocks = []

        if msg.content:
            content_blocks.append({"type": "text", "text": msg.content})

        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    inp = json.loads(tc.function.arguments or "{}")
                except (json.JSONDecodeError, TypeError):
                    inp = {}
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": inp,
                })

        usage = {}
        if resp.usage:
            usage = {
                "input_tokens": resp.usage.prompt_tokens or 0,
                "output_tokens": resp.usage.completion_tokens or 0,
            }

        return LLMResponse(
            content_blocks=content_blocks,
            usage=usage,
            latency_ms=0,  # 由调用方计时
            stop_reason=resp.choices[0].finish_reason,
        )

    # ---------- 主调用 ----------

    async def messages_create(
        self,
        model: str,
        max_tokens: int,
        temperature: float,
        system: str,
        messages: list,
        tools: Optional[list] = None,
        stream: bool = False,
    ) -> LLMResponse:
        start = time.time()
        openai_messages = self._convert_messages(messages, system)
        openai_tools = self._convert_tools(tools) if tools else None

        kwargs = {
            "model": model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if openai_tools:
            kwargs["tools"] = openai_tools
            # DeepSeek 支持 auto/none，用 auto 让模型自主决定
            kwargs["tool_choice"] = "auto"

        try:
            if stream:
                # 流式：收集完整响应后统一转换
                collected_text = ""
                collected_tool_calls = {}
                async with self._client.chat.completions.create(**kwargs, stream=True) as stream_resp:
                    async for chunk in stream_resp:
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta
                        if delta.content:
                            collected_text += delta.content
                        if delta.tool_calls:
                            for tc_delta in delta.tool_calls:
                                idx = tc_delta.index
                                if idx not in collected_tool_calls:
                                    collected_tool_calls[idx] = {
                                        "id": tc_delta.id,
                                        "name": "",
                                        "arguments": "",
                                    }
                                if tc_delta.id:
                                    collected_tool_calls[idx]["id"] = tc_delta.id
                                if tc_delta.function and tc_delta.function.name:
                                    collected_tool_calls[idx]["name"] = tc_delta.function.name
                                if tc_delta.function and tc_delta.function.arguments:
                                    collected_tool_calls[idx]["arguments"] += tc_delta.function.arguments

                # 构造伪响应对象用于转换
                class _FakeMsg:
                    def __init__(self, content, tool_calls):
                        self.content = content
                        self.tool_calls = tool_calls
                class _FakeChoice:
                    def __init__(self, msg, finish_reason):
                        self.message = msg
                        self.finish_reason = finish_reason
                class _FakeUsage:
                    def __init__(self):
                        self.prompt_tokens = 0
                        self.completion_tokens = 0
                class _FakeResp:
                    def __init__(self, msg, finish_reason):
                        self.choices = [_FakeChoice(msg, finish_reason)]
                        self.usage = _FakeUsage()

                tool_call_objs = []
                for idx in sorted(collected_tool_calls.keys()):
                    tc = collected_tool_calls[idx]
                    class _TC:
                        def __init__(self, tc):
                            self.id = tc["id"]
                            class _Fn:
                                def __init__(self, tc):
                                    self.name = tc["name"]
                                    self.arguments = tc["arguments"]
                            self.function = _Fn(tc)
                    tool_call_objs.append(_TC(tc))

                fake_msg = _FakeMsg(collected_text or None, tool_call_objs or None)
                resp = _FakeResp(fake_msg, "stop" if not tool_call_objs else "tool_calls")
                result = self._convert_response(resp)
                result.latency_ms = int((time.time() - start) * 1000)
                return result
            else:
                resp = await self._client.chat.completions.create(**kwargs)
                result = self._convert_response(resp)
                result.latency_ms = int((time.time() - start) * 1000)
                return result
        except Exception as e:
            logger.error(f"[DeepSeekLLM] API 调用失败：{e}")
            raise LLMError(str(e))

# ===== 工厂函数 =====

_llm_client_instance: Optional[LLMClient] = None


def _is_placeholder_key(api_key: str) -> bool:
    """识别占位符 API key（如 sk-ant-your-api-key-here）"""
    if not api_key or not api_key.strip():
        return True
    key = api_key.strip()
    # 占位符标识
    placeholders = ["your-api-key", "your_api_key", "placeholder", "xxx", "sk-ant-your", "changeme", "example"]
    for p in placeholders:
        if p in key.lower():
            return True
    # 真实 key 长度通常 >= 20（DeepSeek ~35，Anthropic ~90+）
    if len(key) < 20:
        return True
    return False


def get_llm_client() -> LLMClient:
    """获取 LLM 客户端单例

    优先级：DeepSeek（OpenAI 兼容）> Anthropic > MockLLM
    任一 provider 配置有效 key 即使用，均无则降级 Mock。
    """
    global _llm_client_instance
    if _llm_client_instance is not None:
        return _llm_client_instance

    # 1. DeepSeek（优先）
    ds_key = getattr(settings, "DEEPSEEK_API_KEY", None) or ""
    if not _is_placeholder_key(ds_key):
        try:
            _llm_client_instance = DeepSeekLLMClient(
                api_key=ds_key,
                base_url=getattr(settings, "DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            )
            logger.info(f"[LLM] 使用 DeepSeek API（model={settings.DEEPSEEK_MODEL}）")
            return _llm_client_instance
        except Exception as e:
            logger.warning(f"[LLM] DeepSeek 初始化失败，尝试下一个 provider：{e}")

    # 2. Anthropic
    api_key = getattr(settings, "ANTHROPIC_API_KEY", None) or ""
    if not _is_placeholder_key(api_key):
        try:
            _llm_client_instance = AnthropicLLMClient(api_key)
            logger.info("[LLM] 使用真实 Anthropic Claude API")
            return _llm_client_instance
        except LLMError as e:
            logger.warning(f"[LLM] Anthropic 初始化失败，降级 Mock：{e}")

    # 3. 降级 Mock
    _llm_client_instance = MockLLMClient()
    logger.info("[LLM] 未配置有效 LLM API Key，使用 MockLLMClient")
    return _llm_client_instance

def get_default_model_name() -> str:
    """根据当前生效的 LLM provider 返回默认模型名"""
    ds_key = getattr(settings, "DEEPSEEK_API_KEY", None) or ""
    if not _is_placeholder_key(ds_key):
        return getattr(settings, "DEEPSEEK_MODEL", "deepseek-chat")
    api_key = getattr(settings, "ANTHROPIC_API_KEY", None) or ""
    if not _is_placeholder_key(api_key):
        return getattr(settings, "ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620")
    return "deepseek-chat"  # Mock 场景也返回 deepseek 模型名（不影响 Mock）
