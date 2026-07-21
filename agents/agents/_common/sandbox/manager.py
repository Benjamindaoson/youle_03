"""SandboxManager — 进程级 sandbox 工厂 + 池(ADR-025)。

# 职责
1. 按 `SANDBOX_PROVIDER` 环境变量挑 provider(`local` / `e2b`)
2. `acquire(task_id)` 返回一个新 sandbox(目前不池化,每次 fresh)
3. `release(sandbox)` 释放
4. `async with manager.session(task_id) as sb: ...` 上下文写法

# 不做什么
S1 不做真池化 / 预热 — 那是 S3 的活(每个 task fresh 已经够 demo)。
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog

from agents._common.sandbox.provider import (
    Sandbox,
    SandboxProvider,
)

log = structlog.get_logger(__name__)

DEFAULT_PROVIDER_NAME = os.getenv("SANDBOX_PROVIDER", "local").strip().lower()


def _make_provider(name: str) -> SandboxProvider:
    if name == "local":
        from agents._common.sandbox.provider_local import make_local_provider
        return make_local_provider()
    if name == "e2b":
        from agents._common.sandbox.provider_e2b import make_e2b_provider
        return make_e2b_provider()
    # 未知 → 回退 local + 警告
    log.warning("sandbox.unknown_provider", name=name, fallback="local")
    from agents._common.sandbox.provider_local import make_local_provider
    return make_local_provider()


class SandboxManager:
    """进程级 sandbox 管理器。"""

    def __init__(self, provider: SandboxProvider | None = None) -> None:
        self._provider: SandboxProvider = provider or _make_provider(DEFAULT_PROVIDER_NAME)

    @property
    def provider_name(self) -> str:
        return self._provider.name

    async def healthy(self) -> bool:
        return await self._provider.healthy()

    async def acquire(
        self,
        *,
        task_id: str | None = None,
        wall_clock_budget_s: int = 600,
        max_stdout_bytes: int = 4 * 1024 * 1024,
        env: dict[str, str] | None = None,
    ) -> Sandbox:
        """获取一个 sandbox。失败抛 SandboxUnavailable。"""
        return await self._provider.acquire(
            task_id=task_id,
            wall_clock_budget_s=wall_clock_budget_s,
            max_stdout_bytes=max_stdout_bytes,
            env=env,
        )

    async def release(self, sandbox: Sandbox) -> None:
        await self._provider.release(sandbox)

    @asynccontextmanager
    async def session(
        self,
        *,
        task_id: str | None = None,
        wall_clock_budget_s: int = 600,
        max_stdout_bytes: int = 4 * 1024 * 1024,
        env: dict[str, str] | None = None,
    ) -> AsyncIterator[Sandbox]:
        """上下文管理器:出 with 块自动 release。

        用法:
            async with manager.session(task_id="t-1") as sb:
                r = await sb.python("print(1+1)")
                print(r.stdout)
        """
        sb = await self.acquire(
            task_id=task_id,
            wall_clock_budget_s=wall_clock_budget_s,
            max_stdout_bytes=max_stdout_bytes,
            env=env,
        )
        try:
            yield sb
        finally:
            try:
                await self.release(sb)
            except Exception as e:
                log.warning(
                    "sandbox.release_fail",
                    sandbox_id=getattr(sb, "sandbox_id", "?"),
                    err=str(e)[:200],
                )


# ─────────────────────────────────────────────────────────────────
# 进程级单例
# ─────────────────────────────────────────────────────────────────
_default_manager: SandboxManager | None = None


def get_default_manager() -> SandboxManager:
    global _default_manager
    if _default_manager is None:
        _default_manager = SandboxManager()
    return _default_manager


def reset_default_manager() -> None:
    """测试用 — 让下一次 get_default_manager 重新挑 provider(读 env)。"""
    global _default_manager
    _default_manager = None
