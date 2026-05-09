"""LangGraph checkpointer 进程级单例 — 从 runner 拆分。"""

from __future__ import annotations

import structlog
from langgraph.checkpoint.memory import InMemorySaver

log = structlog.get_logger(__name__)

_CHECKPOINTER = None  # 由 init_checkpointer() 注入


def init_checkpointer(saver) -> None:
    """app 启动时调一次。"""
    global _CHECKPOINTER
    _CHECKPOINTER = saver


def get_checkpointer():
    global _CHECKPOINTER
    if _CHECKPOINTER is None:
        _CHECKPOINTER = InMemorySaver()
        log.info("lg.checkpointer.in_memory_default")
    return _CHECKPOINTER
