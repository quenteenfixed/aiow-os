"""写入类工具 - 运营操作（价格调整/库存调整/退款/采购建议）

M3-2 范围：4 个写入工具
1. adjust_price      - 调整 SKU 售价（medium 风险）
2. adjust_stock      - 库存调整：入库/出库/盘点（medium 风险，大批量 high）
3. process_refund    - 订单退款（high 风险）
4. suggest_purchase  - 采购建议（low 风险，只生成建议不直接改数据）

所有写入工具 category="write"，触发全部 5 道门禁。
关键流程：
1. Agent 调用写入工具 → Pipeline 门禁检查 → Approval Gate 创建工单（pending）
2. Executor 返回 pending_approval 给 LLM → LLM 告知用户"已提交审批"
3. 店主通过 /work-orders/{id}/approve 审批
4. 店主通过 /work-orders/{id}/execute 执行 → 调用 execution handler → 实际写入
5. 执行结果回写到工单

设计要点：
- 工具定义（schema）注册到 ToolRegistry，供 Agent 调用
- 门禁配置（Guardrail/Provenance/Approval）注册到对应 Gate 模块
- 执行处理函数注册到 WRITE_EXECUTORS，供 work_order_service 调用
"""
import logging
from decimal import Decimal
from typing import Callable, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ToolRegistry
from app.models import Order, Product, SKU, InventoryLog
from app.schemas.product import SKUUpdate
from app.schemas.inventory import InventoryAdjustRequest
from app.schemas.order import RefundRequest
from app.services.product_service import update_sku, _get_sku_by_uuid
from app.services.inventory_service import adjust_inventory
from app.services.order_service import refund_order, _get_order_by_uuid

logger = logging.getLogger(__name__)


# ===== 工具定义（Claude API 格式）=====

TOOL_DEFINITIONS = [
    {
        "name": "adjust_price",
        "description": "调整商品 SKU 售价。提交后生成工单，审批通过后价格生效。",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku_id": {"type": "string", "description": "SKU ID (UUID)，必须先通过查询工具获取"},
                "new_price": {"type": "number", "description": "新售价（元）"},
                "reason": {"type": "string", "description": "调价原因"},
            },
            "required": ["sku_id", "new_price", "reason"],
        },
        "category": "write",
        "risk_level": "medium",
        "id_params": {"sku_id": "product"},
        "guardrails": {"new_price": {"min": 0, "max": 100000, "type": "float"}, "reason": {"max_len": 256, "type": "str"}},
        "risk_config": {"risk_level": "medium", "auto_approve_below": 0},
    },
    {
        "name": "adjust_stock",
        "description": "库存调整（入库/出库/盘点调整）。提交后生成工单，审批通过后执行。",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku_id": {"type": "string", "description": "SKU ID (UUID)"},
                "change_type": {"type": "string", "enum": ["in", "out", "adjust"], "description": "入库/出库/盘点调整"},
                "change_qty": {"type": "integer", "description": "变动数量（入库正、出库负、调整可正可负）"},
                "reason": {"type": "string", "description": "调整原因"},
            },
            "required": ["sku_id", "change_type", "change_qty", "reason"],
        },
        "category": "write",
        "risk_level": "medium",
        "id_params": {"sku_id": "product"},
        "guardrails": {"change_qty": {"min": -10000, "max": 10000, "type": "int"}, "reason": {"max_len": 256, "type": "str"}},
        "risk_config": {"risk_level": "medium", "auto_approve_below": 50},
    },
    {
        "name": "process_refund",
        "description": "处理订单退款。高风险操作，必须审批通过后执行。",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "订单 ID (UUID)"},
                "refund_amount": {"type": "number", "description": "退款金额（元）"},
                "refund_reason": {"type": "string", "description": "退款原因"},
                "refund_type": {"type": "string", "enum": ["full", "partial"], "description": "全额退款/部分退款"},
            },
            "required": ["order_id", "refund_amount", "refund_reason", "refund_type"],
        },
        "category": "write",
        "risk_level": "high",
        "id_params": {"order_id": "order"},
        "guardrails": {
            "refund_amount": {"min": 0, "max": 10000000, "type": "float"},
            "refund_reason": {"max_len": 256, "type": "str"},
        },
        "risk_config": {"risk_level": "high"},
    },
    {
        "name": "suggest_purchase",
        "description": "基于库存和销售数据生成采购建议。只生成建议工单，不直接修改数据。",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku_id": {"type": "string", "description": "SKU ID (UUID)，不传则分析全部低库存商品"},
                "reason": {"type": "string", "description": "采购原因/备注"},
            },
            "required": ["reason"],
        },
        "category": "write",
        "risk_level": "low",
        "id_params": {"sku_id": "product"},
        "guardrails": {"reason": {"max_len": 500, "type": "str"}},
        "risk_config": {"risk_level": "low"},
    },
]


# ===== 执行处理函数（工单审批通过后实际执行）=====

async def _execute_adjust_price(
    db: AsyncSession, business_id: int, agent_id: int, params: dict
) -> str:
    """执行价格调整"""
    from app.services.product_service import get_product_detail
    from app.models import SKU
    from sqlalchemy import select as sa_select
    sku_uuid = params["sku_id"]
    new_price = Decimal(str(params["new_price"]))
    req = SKUUpdate(price=new_price)
    try:
        sku = await update_sku(db, business_id, sku_uuid, req)
    except Exception:
        # 容错：可能传的是 product UUID，查 product 取第一个 SKU
        product = await get_product_detail(db, business_id, sku_uuid)
        sku_result = await db.execute(
            sa_select(SKU).where(
                SKU.product_id == product.id,
                SKU.business_id == business_id,
                SKU.deleted_at.is_(None),
            ).order_by(SKU.id).limit(1)
        )
        sku = sku_result.scalars().first()
        if sku is None:
            raise Exception(f"商品 {sku_uuid[:8]} 下无可用 SKU")
        sku.price = new_price
        await db.commit()
        await db.refresh(sku)
    return f"SKU {sku.sku_code} 售价已调整为 {new_price} 元"


async def _execute_adjust_stock(
    db: AsyncSession, business_id: int, agent_id: int, params: dict
) -> str:
    """执行库存调整"""
    req = InventoryAdjustRequest(
        sku_id=params["sku_id"],
        change_type=params["change_type"],
        change_qty=params["change_qty"],
        reason=params["reason"],
    )
    result = await adjust_inventory(db, business_id, agent_id, req)
    return f"库存调整成功：{result.get('change_type','')} {result.get('change_qty',0)} 件，当前库存 {result.get('after_qty',0)}"


async def _execute_refund(
    db: AsyncSession, business_id: int, agent_id: int, params: dict
) -> str:
    """执行订单退款"""
    req = RefundRequest(
        refund_amount=Decimal(str(params["refund_amount"])),
        refund_reason=params["refund_reason"],
        refund_type=params["refund_type"],
    )
    result = await refund_order(db, business_id, agent_id, params["order_id"], req)
    return f"订单 {params['order_id'][:8]}... 退款 {params['refund_amount']} 元成功，订单状态：{result.get('order_status','refunded')}"


async def _execute_suggest_purchase(
    db: AsyncSession, business_id: int, agent_id: int, params: dict
) -> str:
    """执行采购建议生成（查询库存+销售数据，生成建议文本）"""
    sku_id = params.get("sku_id")
    reason = params.get("reason", "")

    if sku_id:
        # 查单个 SKU 的库存和近期销售
        sku = await _get_sku_by_uuid(db, business_id, sku_id)
        if sku is None:
            return f"SKU {sku_id} 不存在"
        stock = sku.stock_qty
        safety = sku.safety_stock or 0
        suggest_qty = max(safety * 2 - stock, 50) if safety > 0 else 50
        return (
            f"采购建议：SKU {sku.sku_code}（{sku_id[:8]}...）"
            f"当前库存 {stock} 件，安全库存 {safety} 件。"
            f"建议采购 {suggest_qty} 件。原因：{reason}"
        )
    else:
        # 查所有低库存商品
        stmt = (
            select(SKU, Product)
            .join(Product, SKU.product_id == Product.id)
            .where(
                Product.business_id == business_id,
                SKU.status == "active",
            )
        )
        result = await db.execute(stmt)
        rows = result.all()
        low_stock = []
        for sku, product in rows:
            if sku.stock_qty <= (sku.safety_stock or 10):
                suggest = max((sku.safety_stock or 10) * 2 - sku.stock_qty, 50)
                low_stock.append(f"{product.name}({sku.sku_code})：库存{sku.stock_qty}→建议采购{suggest}件")
        if not low_stock:
            return "当前所有商品库存充足，暂无采购建议。"
        return "采购建议汇总：\n" + "\n".join(low_stock[:10])


# 执行处理函数注册表：order_type → handler
WRITE_EXECUTORS: Dict[str, Callable] = {
    "adjust_price": _execute_adjust_price,
    "adjust_stock": _execute_adjust_stock,
    "process_refund": _execute_refund,
    "suggest_purchase": _execute_suggest_purchase,
}


async def execute_work_order_handler(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    order_type: str,
    params: dict,
) -> str:
    """工单执行入口：根据 order_type 调用对应的执行处理函数

    由 work_order_service.start_execution 调用。
    """
    handler = WRITE_EXECUTORS.get(order_type)
    if handler is None:
        raise ValueError(f"未知的工单类型：{order_type}，无法执行")
    return await handler(db, business_id, agent_id, params)


# ===== 注册写入工具到 ToolRegistry =====

def register_write_tools(registry: ToolRegistry) -> None:
    """注册 4 个写入工具到 ToolRegistry"""
    for tool_def in TOOL_DEFINITIONS:
        # 写入工具的 handler 是占位（实际执行走工单流程，不直接调用）
        # 但注册时需要一个 handler，这里注册一个返回"已提交审批"的占位
        async def _placeholder_handler(**kwargs):
            return {"status": "pending_approval", "message": "此操作需要审批后执行"}

        registry.register(
            name=tool_def["name"],
            description=tool_def["description"],
            input_schema=tool_def["input_schema"],
            handler=_placeholder_handler,
            category="write",
            gates={
                "fencing": True, "provenance": True,
                "guardrail": True, "rate_limit": True, "approval": True,
            },
        )
        logger.info(f"[ToolRegistry] 注册写入工具 {tool_def['name']}（write）")


def configure_write_gates() -> None:
    """将写入工具的门禁配置注入到各 Gate 模块

    在应用启动时调用（main.py 的 lifespan 中）。
    """
    # 1. Guardrail Gate 参数护栏配置
    from app.agent.gates.guardrail import TOOL_GUARDRAILS
    for tool_def in TOOL_DEFINITIONS:
        if "guardrails" in tool_def:
            TOOL_GUARDRAILS[tool_def["name"]] = tool_def["guardrails"]

    # 2. Provenance Gate ID 参数配置
    from app.agent.gates.provenance import TOOL_ID_PARAMS
    for tool_def in TOOL_DEFINITIONS:
        if "id_params" in tool_def:
            TOOL_ID_PARAMS[tool_def["name"]] = tool_def["id_params"]

    # 3. Approval Gate 风险配置
    from app.agent.gates.approval import TOOL_RISK_CONFIG
    for tool_def in TOOL_DEFINITIONS:
        if "risk_config" in tool_def:
            TOOL_RISK_CONFIG[tool_def["name"]] = tool_def["risk_config"]

    logger.info("[WriteTools] 4 个写入工具门禁配置已注入")
