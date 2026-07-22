from __future__ import annotations

import builtins
from typing import Any

import pytest


@pytest.mark.asyncio
async def test_checkpointer_inmemory_setting_skips_postgres_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """LANGGRAPH_CHECKPOINT_INMEMORY from settings should avoid any Postgres connection path."""
    from agents.orchestrator_agent.langgraph_runner import checkpointer

    from app.config import settings

    monkeypatch.setattr(checkpointer, "_saver", None)
    monkeypatch.setattr(checkpointer, "_psyco_pool", None)
    monkeypatch.setattr(settings, "LANGGRAPH_CHECKPOINT_INMEMORY", True)

    original_import = builtins.__import__
    imported_psycopg_pool = False

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        nonlocal imported_psycopg_pool
        if name == "psycopg_pool":
            imported_psycopg_pool = True
            raise AssertionError("postgres pool should not be imported in in-memory mode")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    saver = await checkpointer.init_postgres_checkpointer(
        "postgresql+asyncpg://haole:haole_dev@localhost:5432/haole"
    )

    assert saver.__class__.__name__ == "InMemorySaver"
    assert imported_psycopg_pool is False

    await checkpointer.close_postgres_checkpointer()


@pytest.mark.asyncio
async def test_checkpointer_falls_back_to_memory_when_postgres_fails_in_dev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient local Postgres failure must not crash the development API."""
    import psycopg_pool
    from agents.orchestrator_agent.langgraph_runner import checkpointer

    from app.config import settings

    class FailingPool:
        def __init__(self, **_: Any) -> None:
            pass

        async def open(self, *, wait: bool) -> None:
            raise OSError("postgres unavailable")

        async def close(self) -> None:
            pass

    monkeypatch.setattr(checkpointer, "_saver", None)
    monkeypatch.setattr(checkpointer, "_psyco_pool", None)
    monkeypatch.setattr(settings, "ENV", "dev")
    monkeypatch.setattr(settings, "LANGGRAPH_CHECKPOINT_INMEMORY", False)
    monkeypatch.setattr(psycopg_pool, "AsyncConnectionPool", FailingPool)

    saver = await checkpointer.init_postgres_checkpointer(
        "postgresql+asyncpg://haole:haole_dev@localhost:5432/haole"
    )

    assert saver.__class__.__name__ == "InMemorySaver"
    await checkpointer.close_postgres_checkpointer()
