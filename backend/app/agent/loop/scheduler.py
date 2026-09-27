"""OUPDEL 循环调度器 - 基于 asyncio 的轻量级定时任务

设计要点：
1. 应用启动时调用 scheduler.start()，每隔 SCAN_INTERVAL_SECONDS 扫描一次 agent_loops
2. 对 enabled=True 且 next_run_at <= now 的循环，触发 LoopEngine.run_once
3. 每个循环的触发是串行的（避免并发写同一商户数据）
4. 支持手动触发（trigger_loop）和启停（pause_loop / resume_loop）
5. 应用关闭时调用 scheduler.stop()，优雅终止后台任务

不使用 APScheduler / Celery 等重型依赖，纯 asyncio 实现：
- 维护一个 _task: asyncio.Task，运行 _run_forever 循环
- 每次扫描查询数据库，过滤到期的循环
- 调用 LoopEngine.run_once 触发，每个循环独立 try/except
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Set

from sqlalchemy import select

from app.database import async_session_factory
from app.models.loop import AgentLoop
from app.agent.loop.engine import get_loop_engine

logger = logging.getLogger(__name__)


# 扫描间隔：默认 60 秒扫描一次
SCAN_INTERVAL_SECONDS = 60


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class LoopScheduler:
    """OUPDEL 循环调度器 - 单例"""

    _instance: Optional["LoopScheduler"] = None

    @classmethod
    def get_instance(cls) -> "LoopScheduler":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running: bool = False
        # 正在执行的循环 ID 集合（避免同 loop 并发执行）
        self._active_loops: Set[int] = set()
        # 暂停的循环 ID 集合（手动暂停的，不受 enabled 影响）
        self._paused_loops: Set[int] = set()

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def start(self) -> None:
        """启动调度器（在 FastAPI lifespan 中调用）"""
        if self.is_running:
            logger.warning("[LoopScheduler] 已在运行，忽略重复启动")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_forever())
        logger.info(f"[LoopScheduler] 启动，扫描间隔 {SCAN_INTERVAL_SECONDS}s")

    async def stop(self) -> None:
        """停止调度器（在 FastAPI lifespan 中调用）"""
        self._running = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"[LoopScheduler] 停止时异常：{e}")
        self._task = None
        logger.info("[LoopScheduler] 已停止")

    def pause_loop(self, loop_id: int) -> None:
        """手动暂停某个循环（不影响 enabled 字段）"""
        self._paused_loops.add(loop_id)
        logger.info(f"[LoopScheduler] 手动暂停循环 {loop_id}")

    def resume_loop(self, loop_id: int) -> None:
        """恢复某个循环"""
        self._paused_loops.discard(loop_id)
        logger.info(f"[LoopScheduler] 恢复循环 {loop_id}")

    async def trigger_loop(
        self, business_id: int, agent_id: int, trigger_type: str = "manual"
    ) -> dict:
        """手动触发一次循环（不受 enabled 限制）

        Returns:
            LoopEngine.run_once 的返回值
        """
        engine = get_loop_engine()
        async with async_session_factory() as db:
            result = await engine.run_once(
                db, business_id, agent_id, trigger_type=trigger_type
            )
        return result

    async def _run_forever(self) -> None:
        """调度主循环"""
        while self._running:
            try:
                await self._scan_and_run()
            except asyncio.CancelledError:
                logger.info("[LoopScheduler] 收到取消信号，退出")
                break
            except Exception as e:
                logger.error(f"[LoopScheduler] 扫描异常：{e}", exc_info=True)
            await asyncio.sleep(SCAN_INTERVAL_SECONDS)

    async def _scan_and_run(self) -> None:
        """扫描到期的循环并触发执行"""
        now = _now_naive()
        try:
            async with async_session_factory() as db:
                stmt = select(AgentLoop).where(
                    AgentLoop.enabled == True,  # noqa: E712
                    AgentLoop.next_run_at.is_not(None),
                    AgentLoop.next_run_at <= now,
                )
                loops = (await db.execute(stmt)).scalars().all()
        except Exception as e:
            logger.error(f"[LoopScheduler] 查询循环列表失败：{e}")
            return

        if not loops:
            return

        logger.info(f"[LoopScheduler] 扫描到 {len(loops)} 个待执行循环")

        engine = get_loop_engine()
        for loop in loops:
            if loop.id in self._paused_loops:
                logger.info(f"[LoopScheduler] 循环 {loop.id} 已暂停，跳过")
                continue
            if loop.id in self._active_loops:
                logger.info(f"[LoopScheduler] 循环 {loop.id} 正在执行，跳过")
                continue

            # 触发执行（每个循环独立 try/except）
            self._active_loops.add(loop.id)
            asyncio.create_task(self._run_one_loop(engine, loop))

    async def _run_one_loop(self, engine, loop: AgentLoop) -> None:
        """执行单个循环（在独立 task 中）"""
        try:
            async with async_session_factory() as db:
                await engine.run_once(
                    db, loop.business_id, loop.agent_id,
                    trigger_type="scheduled",
                )
        except Exception as e:
            logger.error(
                f"[LoopScheduler] 循环 {loop.id}（agent={loop.agent_id}）执行失败：{e}",
                exc_info=True,
            )
        finally:
            self._active_loops.discard(loop.id)


def get_scheduler() -> LoopScheduler:
    """获取调度器单例"""
    return LoopScheduler.get_instance()
