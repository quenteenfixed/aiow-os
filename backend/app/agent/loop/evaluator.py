"""OUPDEL - Learn 步骤

6. Learn：评估已执行操作的效果，写入记忆

设计要点：
- 本阶段（M3-3）做基础评估：
  - 统计本轮创建的工单数（已自动执行 / 待审批 / 失败）
  - 对自动执行的工单，记录其执行结果摘要
  - 写入 AgentMemory（feedback 类型），供 M4-1 记忆系统接入
- 完整的效果追踪（对比执行前后指标）留 M4-1 实现
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentMemory, WorkOrder, ExecutionJob
from app.agent.types import utcnow_naive

logger = logging.getLogger(__name__)


async def evaluate(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    run_id: int,
    execution_results: dict,
    anomalies: list,
    observe_data: dict,
) -> dict:
    """Learn：评估本轮执行结果，写入记忆

    Args:
        execution_results: loop_executor.execute() 的返回值
        anomalies: observer 检测到的异常列表
        observe_data: observer 采集的指标

    Returns:
        {
            "summary": "...",
            "work_order_stats": {...},
            "memory_written": True/False,
            "memory_id": ...,
        }
    """
    work_order_ids = execution_results.get("work_order_ids", [])
    results = execution_results.get("results", [])
    alerts = execution_results.get("alerts", [])

    # 统计工单状态
    auto_completed = sum(1 for r in results if r.get("status") == "auto_completed")
    auto_failed = sum(1 for r in results if "failed" in r.get("status", ""))
    pending_approval = sum(1 for r in results if r.get("status") == "pending_approval")
    alert_count = len(alerts)

    summary = (
        f"本轮循环检测到 {len(anomalies)} 个异常，"
        f"创建工单 {len(work_order_ids)} 个（自动完成 {auto_completed}，"
        f"待审批 {pending_approval}，失败 {auto_failed}），"
        f"生成纯告警 {alert_count} 条。"
    )

    evaluation = {
        "summary": summary,
        "work_order_stats": {
            "total": len(work_order_ids),
            "auto_completed": auto_completed,
            "auto_failed": auto_failed,
            "pending_approval": pending_approval,
            "alert_only": alert_count,
        },
        "anomaly_count": len(anomalies),
        "memory_written": False,
    }

    # 写入 AgentMemory（feedback 类型）
    # M4-1 记忆系统完整接入后可做向量检索；M3-3 阶段只做基础写入
    try:
        memory = AgentMemory(
            agent_id=agent_id,
            business_id=business_id,
            memory_type="feedback",
            title=f"OUPDEL 循环 #{run_id} 评估",
            content=summary,
            tags=["ouupdel", "loop", f"run_{run_id}"],
            importance=3,
            source="loop",
            source_id=run_id,
            metadata_={
                "run_id": run_id,
                "work_order_ids": [int(x) for x in work_order_ids],
                "anomaly_count": len(anomalies),
                "observe_summary": {
                    "low_stock_count": observe_data.get("inventory", {}).get("low_stock_count", 0),
                    "out_of_stock_count": observe_data.get("inventory", {}).get("out_of_stock_count", 0),
                    "today_sales_amount": observe_data.get("sales", {}).get("today_amount", 0),
                    "expiring_count": observe_data.get("expiring", {}).get("count", 0),
                },
            },
        )
        db.add(memory)
        await db.commit()
        await db.refresh(memory)
        evaluation["memory_written"] = True
        evaluation["memory_id"] = memory.id
        logger.info(f"[Evaluator] 写入记忆 {memory.id}（run={run_id}）")
    except Exception as e:
        logger.warning(f"[Evaluator] 写入记忆失败：{e}")
        evaluation["memory_error"] = str(e)

    return evaluation
