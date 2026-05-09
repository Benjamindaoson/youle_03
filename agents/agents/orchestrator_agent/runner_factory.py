"""Runner 工厂。

调用方统一从这里拿主编排器，当前实现固定为 LangGraph。
保留工厂层是为了让 API / 服务层不依赖具体 runner 模块路径。

# ADR-019(S1):动态规划开关
`is_dynamic_plan_enabled()` 暴露给上游(messages.py 在 S2 集成),
判断是否在 Skill 不命中时调 Planner 走动态 plan 路径。
默认关闭,production 行为完全不变。
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession

from agents.orchestrator_agent.langgraph_runner import LangGraphTaskRunner


def make_runner(
    session: AsyncSession, *, dispatcher=None, publisher=None
) -> LangGraphTaskRunner:
    """返回项目唯一的主编排器实现。"""
    return LangGraphTaskRunner(session, dispatcher=dispatcher, publisher=publisher)


def is_dynamic_plan_enabled() -> bool:
    """ADR-019:动态规划路径开关(默认 false)。

    与 `agents.orchestrator_agent.planner.entry.is_dynamic_plan_enabled()` 等价 —
    在 runner_factory 也暴露一份,方便 messages.py / API 层不引入 planner 包
    就能判断。"""
    return os.getenv("ENABLE_DYNAMIC_PLAN", "false").lower() in {"1", "true", "yes"}
