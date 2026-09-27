"""OUPDEL - Execute 步骤

5. Execute：根据 Decide 结果创建工单
   - should_create_work_order=True 的决策创建 pending 工单
   - auto_approve=True 的工单自动 approve + 自动 execute

设计要点：
- 工单 order_type 与 write_tools.py 的 WRITE_EXECUTORS 一致
- alert_only 的决策不创建工单，但写入 evaluation 供后续告警系统使用
- 自动执行的工单会调用 work_order_service.start_execution（内部调 write_tools handler）
"""
import logging
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.work_order_service import (
    create_work_order, approve_work_order, start_execution,
)
from app.agent.types import utcnow_naive

logger = logging.getLogger(__name__)


async def execute(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    decisions: list,
) -> dict:
    """Execute：根据决策列表创建工单

    Returns:
        {
            "work_order_ids": [1, 2, ...],
            "work_order_count": N,
            "results": [{"decision": ..., "work_order_id": ..., "status": ..., "error": ...}, ...],
            "alerts": [{...}],  # alert_only 决策
        }
    """
    work_order_ids = []
    results = []
    alerts = []

    for decision in decisions:
        if not decision.get("should_create_work_order", False):
            # alert_only：不创建工单，记录到 alerts
            if decision.get("action") == "alert_only":
                alerts.append({
                    "anomaly_type": decision.get("anomaly_type"),
                    "anomaly_severity": decision.get("anomaly_severity"),
                    "title": decision.get("title"),
                    "reason": decision.get("reason"),
                    "risk_level": decision.get("risk_level"),
                })
            results.append({
                "action": decision.get("action"),
                "status": "alert_only",
                "message": "纯告警，未创建工单",
            })
            continue

        # 创建工单
        try:
            wo = await create_work_order(
                db, business_id, agent_id,
                order_type=decision.get("order_type"),
                title=decision.get("title") or f"自主循环·{decision.get('action')}",
                description=decision.get("reason"),
                reason=decision.get("reason"),
                expected_effect=_expected_effect(decision),
                risk_level=decision.get("risk_level", "medium"),
                params=decision.get("params") or {},
                submitter_agent_id=agent_id,
            )
            work_order_ids.append(wo.id)

            # 自动审批 + 执行（L2+ 低风险、L3+ 中风险、L4 全自动）
            if decision.get("auto_approve"):
                wo, err = await approve_work_order(
                    db, business_id, wo.id, approver_id=0,  # 0 表示 Agent 自主审批
                    comment=f"自主级别 {decision.get('risk_level')} 自动审批",
                )
                if err:
                    logger.warning(f"[LoopExecutor] 工单 {wo.id} 自动审批失败：{err}")
                    results.append({
                        "action": decision.get("action"),
                        "work_order_id": wo.id,
                        "status": "auto_approve_failed",
                        "error": err,
                    })
                    continue

                wo, err = await start_execution(db, business_id, wo.id)
                if err:
                    logger.warning(f"[LoopExecutor] 工单 {wo.id} 自动执行失败：{err}")
                    results.append({
                        "action": decision.get("action"),
                        "work_order_id": wo.id,
                        "status": "auto_execute_failed",
                        "error": err,
                    })
                else:
                    exec_status = wo.status  # completed / failed
                    results.append({
                        "action": decision.get("action"),
                        "work_order_id": wo.id,
                        "status": f"auto_{exec_status}",
                        "execution_result": (
                            wo.execution_job.result if wo.execution_job else None
                        ),
                    })
            else:
                # 仅创建工单，等待人工审批
                results.append({
                    "action": decision.get("action"),
                    "work_order_id": wo.id,
                    "status": "pending_approval",
                    "message": "已创建工单，等待人工审批",
                })

        except Exception as e:
            logger.error(
                f"[LoopExecutor] 创建工单失败（action={decision.get('action')}）：{e}",
                exc_info=True,
            )
            results.append({
                "action": decision.get("action"),
                "status": "create_failed",
                "error": f"{type(e).__name__}: {str(e)}",
            })

    return {
        "work_order_ids": work_order_ids,
        "work_order_count": len(work_order_ids),
        "results": results,
        "alerts": alerts,
    }


def _expected_effect(decision: dict) -> str:
    """根据动作类型生成预期效果描述"""
    action = decision.get("action")
    if action == "suggest_purchase":
        return "补货至安全库存水位，避免缺货"
    if action == "adjust_price":
        return "调整售价促进销售或临期商品清仓"
    if action == "adjust_stock":
        return "调整库存到合理水位"
    if action == "process_refund":
        return "完成订单退款"
    return "运营优化"
