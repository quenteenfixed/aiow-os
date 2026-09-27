"""OUPDEL - Plan + Decide 步骤

3. Plan：针对异常生成解决方案（如补货、调价、促销、纯告警）
4. Decide：风险评估，标注风险等级，决定是否自动执行

设计要点：
- Plan 接收异常列表，每个异常映射到 suggest_purchase / adjust_price / alert_only 等动作
- Decide 根据自主级别（L0~L4）决定是否自动执行：
  - L0：全人工，所有方案只生成工单待审批
  - L1：建议级别，只生成工单
  - L2：低风险自动执行（low 风险的工单自动 approve）
  - L3：中风险自动执行（medium 风险也自动 approve）
  - L4：全自动（high 风险也自动 approve）
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# 工单类型映射
ACTION_TO_ORDER_TYPE = {
    "suggest_purchase": "suggest_purchase",
    "adjust_price": "adjust_price",
    "adjust_stock": "adjust_stock",
    "process_refund": "process_refund",
    "alert_only": "alert",  # 纯告警不创建工单
}

# 风险等级映射
ACTION_DEFAULT_RISK = {
    "suggest_purchase": "low",
    "adjust_price": "medium",
    "adjust_stock": "medium",
    "process_refund": "high",
    "alert_only": "low",
}


def plan(anomalies: list) -> list:
    """Plan：将异常列表转换为解决方案列表

    Returns:
        [
            {
                "anomaly_type": "low_stock",
                "anomaly_severity": "P1",
                "title": "...",
                "action": "suggest_purchase",
                "params": {...},
                "risk_level": "low",
            },
            ...
        ]
    """
    plans = []
    for anomaly in anomalies:
        action = anomaly.get("suggested_action", "alert_only")
        params = anomaly.get("suggested_params", {}) or {}
        risk = ACTION_DEFAULT_RISK.get(action, "low")

        plans.append({
            "anomaly_type": anomaly.get("type"),
            "anomaly_severity": anomaly.get("severity"),
            "anomaly_title": anomaly.get("title"),
            "anomaly_detail": anomaly.get("detail"),
            "action": action,
            "title": _build_plan_title(anomaly, action),
            "params": params,
            "risk_level": risk,
            "reason": params.get("reason", anomaly.get("title")),
        })
    return plans


def _build_plan_title(anomaly: dict, action: str) -> str:
    """生成工单标题"""
    anomaly_title = anomaly.get("title", "")
    if action == "suggest_purchase":
        return f"自主循环·采购建议 - {anomaly_title}"
    if action == "adjust_price":
        return f"自主循环·价格调整 - {anomaly_title}"
    if action == "adjust_stock":
        return f"自主循环·库存调整 - {anomaly_title}"
    if action == "process_refund":
        return f"自主循环·退款处理 - {anomaly_title}"
    return f"自主循环·告警 - {anomaly_title}"


# 自主级别 → 可自动执行的风险等级
AUTONOMY_AUTO_RISK = {
    "L0": set(),          # 全人工
    "L1": set(),          # 仅建议
    "L2": {"low"},        # 低风险自动
    "L3": {"low", "medium"},  # 中风险自动
    "L4": {"low", "medium", "high"},  # 全自动
}


def decide(plans: list, autonomy_level: str = "L2") -> list:
    """Decide：风险评估，决定每个方案的执行方式

    Returns:
        [
            {
                "action": "suggest_purchase",
                "title": "...",
                "params": {...},
                "risk_level": "low",
                "auto_execute": True/False,
                "should_create_work_order": True/False,
                "reason": "...",
            },
            ...
        ]
    """
    auto_risks = AUTONOMY_AUTO_RISK.get(autonomy_level, set())
    decisions = []

    for plan in plans:
        action = plan.get("action", "alert_only")
        risk = plan.get("risk_level", "low")
        # alert_only 不创建工单
        should_create = action != "alert_only" and action in ACTION_TO_ORDER_TYPE
        # 自动执行条件：自主级别允许 + 是真实写入动作
        auto_execute = should_create and risk in auto_risks

        decisions.append({
            "action": action,
            "order_type": ACTION_TO_ORDER_TYPE.get(action, action),
            "title": plan.get("title"),
            "params": plan.get("params"),
            "risk_level": risk,
            "should_create_work_order": should_create,
            "auto_execute": auto_execute,
            "auto_approve": auto_execute,
            "reason": plan.get("reason"),
            "anomaly_type": plan.get("anomaly_type"),
            "anomaly_severity": plan.get("anomaly_severity"),
        })

    return decisions
