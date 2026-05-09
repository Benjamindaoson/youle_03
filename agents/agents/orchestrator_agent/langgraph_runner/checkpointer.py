"""Checkpointer 工厂 — 选 InMemorySaver(开发)或 AsyncPostgresSaver(生产)。

PostgresSaver 用独立连接池(不挂 SQLAlchemy session)以避免 transaction 嵌套。
表自动 setup(LangGraph 自带 migration)。
"""

from __future__ import annotations

import os

import structlog

from app.config import settings

log = structlog.get_logger(__name__)


# ── 全局持有的 saver 实例(app lifespan 管理)──
_saver = None
_psyco_pool = None


async def init_postgres_checkpointer(database_url: str | None = None):
    """app 启动时调一次。返回 saver 实例(可传给 init_checkpointer)。"""
    global _saver, _psyco_pool
    if _saver is not None:
        return _saver

    url = database_url or os.getenv("LANGGRAPH_CHECKPOINT_URL") or os.getenv("DATABASE_URL")
    force_in_memory = (
        settings.LANGGRAPH_CHECKPOINT_INMEMORY
        or os.getenv("LANGGRAPH_CHECKPOINT_INMEMORY", "").lower() == "true"
    )
    if not url or url.startswith("sqlite") or force_in_memory:
        from langgraph.checkpoint.memory import InMemorySaver

        if not settings.is_dev and not force_in_memory:
            raise RuntimeError(
                "非 dev 环境必须提供 Postgres 类 DATABASE_URL / LANGGRAPH_CHECKPOINT_URL 作为 LangGraph checkpoint;"
                "若确需内存图谱请显式设置 LANGGRAPH_CHECKPOINT_INMEMORY=true。"
            ) from None

        log.info(
            "lg.checkpointer.in_memory",
            reason="forced" if force_in_memory else "no postgres url",
        )
        _saver = InMemorySaver()
        return _saver

    # SQLAlchemy URL → libpq URL(兼容 asyncpg / psycopg async 驱动写法)
    pq_url = (
        url.replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+psycopg://", "postgresql://")
    )
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg_pool import AsyncConnectionPool

        _psyco_pool = AsyncConnectionPool(
            conninfo=pq_url,
            max_size=int(os.getenv("LANGGRAPH_PG_POOL_MAX", "10")),
            kwargs={"autocommit": True, "prepare_threshold": 0},
            open=False,
        )
        await _psyco_pool.open(wait=True)
        _saver = AsyncPostgresSaver(_psyco_pool)
        await _saver.setup()  # 创建 langgraph 表
        log.info("lg.checkpointer.postgres", url_redacted=pq_url.split("@")[-1])
        return _saver
    except Exception as e:
        log.warning("lg.checkpointer.postgres_failed", err=str(e))
        if not settings.is_dev:
            raise RuntimeError(
                "LangGraph Postgres checkpointer 初始化失败;非 dev 环境禁止静默降级到 InMemory。"
            ) from e
        _saver = InMemorySaver()
        return _saver


async def close_postgres_checkpointer() -> None:
    global _saver, _psyco_pool
    if _psyco_pool is not None:
        try:
            await _psyco_pool.close()
        except Exception as e:
            log.warning("lg.checkpointer.close_failed", err=str(e))
    _saver = None
    _psyco_pool = None
