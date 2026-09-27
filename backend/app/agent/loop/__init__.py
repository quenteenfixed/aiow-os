"""OUPDEL 自主运营循环模块

OUPDEL = Observe + Understand + Plan + Decide + Execute + Learn

模块构成：
- observer.py     : O+U 步骤（采集指标 + 异常检测）
- planner.py      : P+D 步骤（方案生成 + 风险评估）
- loop_executor.py: E 步骤（创建工单）
- evaluator.py    : L 步骤（效果评估 + 写入记忆）
- engine.py       : 编排六步循环
- scheduler.py    : 定时调度器
"""
from app.agent.loop.engine import LoopEngine, get_loop_engine

__all__ = ["LoopEngine", "get_loop_engine"]
