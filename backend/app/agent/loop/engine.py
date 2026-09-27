"""OUPDEL 引擎 - 编排 Observe→Understand→Plan→Decide→Execute→Learn 六步

调用方式：
    from app.agent.loop.engine import LoopEngine
    engine = LoopEngine()
    result = await engine.run_once(db, business_id, agent_id, trigger_type="manual")

设计要点：
1. 每次循环都创建 AgentLoopRun 记录，各步骤产物逐步 update_run
2. 任意步骤异常都不影响已写入的产物（捕获后写入 error_message）
3. 循环配置不存在时自动创建默认配置
4. 循环禁用或 Agent 不可用时返回 skipped
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop.observer import observe, understand
from app.agent.loop.planner import plan, decide
from app.agent.loop.loop_executor import execute as loop_execute
from app.agent.loop.evaluator import evaluate
from app.services.loop_service import (
    get_or_create_loop, create_run, update_run, mark_loop_run,
)
from app.services.agent_service import _get_agent_by_id
from app.services.alert_service import create_alerts_batch

logger = logging.getLogger(__name__)


class LoopEngine:
    """OUPDEL 循环引擎 - 单例"""

    _instance: Optional["LoopEngine"] = None

    @classmethod
    def get_instance(cls) -> "LoopEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def run_once(
        self,
        db: AsyncSession,
        business_id: int,
        agent_id: int,
        trigger_type: str = "scheduled",
    ) -> dict:
        """执行一次完整的 OUPDEL 循环

        Returns:
            {
                "loop_id": ...,
                "run_id": ...,
                "run_status": "completed/failed/skipped",
                "anomaly_count": ...,
                "work_order_count": ...,
                "evaluation": {...},
                "error": "...",  # 失败时
            }
        """
        started_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # 1. 校验 Agent
        agent = await _get_agent_by_id(db, business_id, agent_id)
        if agent is None:
            return {
                "run_status": "skipped",
                "error": "Agent 不存在或无权访问",
            }
        if agent.status not in ("ready", "running"):
            return {
                "run_status": "skipped",
                "error": f"Agent 状态为 {agent.status}，跳过循环",
            }

        # 2. 获取或创建循环配置
        loop = await get_or_create_loop(db, business_id, agent_id)

        # 手动触发不校验 enabled；定时触发必须 enabled=True
        if trigger_type == "scheduled" and not loop.enabled:
            return {
                "loop_id": loop.id,
                "run_status": "skipped",
                "error": "循环已停用",
            }

        # 3. 创建运行记录
        run = await create_run(
            db, business_id, agent_id, loop.id, trigger_type=trigger_type
        )
        run_id = run.id

        # 更新循环的 last_run_at / next_run_at
        await mark_loop_run(db, business_id, loop.id, started_at=started_at)

        result = {
            "loop_id": loop.id,
            "run_id": run_id,
            "run_status": "running",
        }

        # 4. 执行 OUPDEL 六步
        try:
            # O - Observe
            observe_data = await observe(
                db, business_id, loop.sensitivity, loop.config,
            )
            await update_run(
                db, business_id, run_id, observe_data=observe_data,
            )

            # U - Understand
            anomalies = understand(observe_data, loop.sensitivity)
            await update_run(
                db, business_id, run_id,
                anomalies=anomalies,
                anomaly_count=len(anomalies),
            )
            result["anomaly_count"] = len(anomalies)

            # M3-4: 异常 → 告警（去重 + 分级）
            alert_result = {"created": 0, "deduplicated": 0, "errors": []}
            if anomalies:
                alert_data = [_anomaly_to_alert(a) for a in anomalies]
                try:
                    alert_result = await create_alerts_batch(
                        db, business_id, alert_data,
                        dedup_window_hours=24,
                    )
                    result["alerts"] = alert_result
                    logger.info(
                        f"[LoopEngine] 循环 #{run_id} 告警生成："
                        f"created={alert_result['created']} "
                        f"dedup={alert_result['deduplicated']}"
                    )
                except Exception as e:
                    logger.warning(f"[LoopEngine] 告警生成失败：{e}")
                    result["alerts"] = {"error": str(e)}

            # 没有异常 → 直接完成
            if not anomalies:
                await update_run(
                    db, business_id, run_id,
                    run_status="completed",
                    evaluation={
                        "summary": "本轮循环未检测到异常，无需执行操作。",
                        "anomaly_count": 0,
                    },
                )
                result["run_status"] = "completed"
                result["evaluation"] = {"summary": "无异常"}
                logger.info(f"[LoopEngine] 循环 #{run_id} 完成：无异常")
                return result

            # P - Plan
            plans = plan(anomalies)
            await update_run(db, business_id, run_id, plans=plans)

            # D - Decide
            decisions = decide(plans, loop.autonomy_level)
            await update_run(db, business_id, run_id, decisions=decisions)

            # E - Execute
            execution_results = await loop_execute(
                db, business_id, agent_id, decisions,
            )
            await update_run(
                db, business_id, run_id,
                work_order_ids=execution_results.get("work_order_ids", []),
                work_order_count=execution_results.get("work_order_count", 0),
            )
            result["work_order_count"] = execution_results.get("work_order_count", 0)
            result["work_order_ids"] = execution_results.get("work_order_ids", [])

            # L - Learn
            evaluation = await evaluate(
                db, business_id, agent_id, run_id,
                execution_results, anomalies, observe_data,
            )
            await update_run(
                db, business_id, run_id,
                run_status="completed",
                evaluation=evaluation,
            )
            result["run_status"] = "completed"
            result["evaluation"] = evaluation

            logger.info(
                f"[LoopEngine] 循环 #{run_id} 完成："
                f"检测到 {len(anomalies)} 个异常，"
                f"创建 {result['work_order_count']} 个工单"
            )
            return result

        except Exception as e:
            logger.error(
                f"[LoopEngine] 循环 #{run_id} 失败：{e}", exc_info=True
            )
            await update_run(
                db, business_id, run_id,
                run_status="failed",
                error_message=f"{type(e).__name__}: {str(e)}",
            )
            result["run_status"] = "failed"
            result["error"] = str(e)
            return result


def get_loop_engine() -> LoopEngine:
    """获取 LoopEngine 单例"""
    return LoopEngine.get_instance()


def _anomaly_to_alert(anomaly: dict) -> dict:
    """把异常映射为告警数据（供 alert_service.create_alerts_batch）"""
    anomaly_type = anomaly.get("type", "unknown")
    severity = anomaly.get("severity", "P2")
    # 异常类型 → 告警类型
    type_map = {
        "out_of_stock": "inventory",
        "low_stock": "inventory",
        "sales_drop": "sales",
        "expiring_excess": "expiring",
    }
    alert_type = type_map.get(anomaly_type, "system")
    return {
        "alert_type": alert_type,
        "level": severity,
        "title": anomaly.get("title", ""),
        "content": str(anomaly.get("detail", "")),
        "source": "loop",
    }
