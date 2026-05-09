"""Sandbox Provider 抽象(ADR-025)。

三个核心概念:
  - `SandboxProvider`:工厂,负责 `acquire(task_id)` / `release(sandbox)`
  - `Sandbox`:单个沙箱实例,提供 exec / write_file / read_file / snapshot
  - `ExecResult`:单次执行返回(stdout / stderr / returncode / duration)

设计原则:
  1. **Protocol-based**:不强迫 provider 继承同一基类,只要满足接口即可
  2. **async-first**:所有 I/O 异步
  3. **生命周期清晰**:acquire 返回的对象必须 release(`async with` 友好)
  4. **预算硬上限**:每个 sandbox 有总 wall-clock + 总 stdout 字节上限
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class SandboxUnavailable(RuntimeError):
    """provider 不可用 — SDK 未装 / API key 缺失 / 健康检查失败。"""


class SandboxBudgetExceeded(RuntimeError):
    """超出 wall-clock 或字节上限。"""


@dataclass
class ExecResult:
    """单次 exec 的结果。"""

    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    duration_ms: int = 0
    truncated: bool = False
    timed_out: bool = False
    error: str | None = None  # provider 自己挂(网络等)时填

    def ok(self) -> bool:
        return (
            self.returncode == 0
            and not self.timed_out
            and self.error is None
        )


@runtime_checkable
class Sandbox(Protocol):
    """单个沙箱实例 — provider 自己实现。

    实现方应当**显式释放**资源:支持 `async with sandbox: ...`,
    或者由 SandboxManager 集中 release。
    """

    sandbox_id: str
    provider_name: str
    task_id: str | None
    created_at: float

    async def exec(
        self,
        cmd: str,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_s: int | None = None,
        max_stdout_bytes: int | None = None,
    ) -> ExecResult:
        """执行 shell 命令。"""
        ...

    async def python(
        self,
        code: str,
        *,
        timeout_s: int | None = None,
        max_stdout_bytes: int | None = None,
    ) -> ExecResult:
        """执行 Python 代码片段。"""
        ...

    async def write_file(self, path: str, content: bytes | str) -> None:
        ...

    async def read_file(self, path: str, *, max_bytes: int | None = None) -> bytes:
        ...

    async def list_dir(self, path: str = ".") -> list[str]:
        ...

    async def close(self) -> None:
        """释放底层资源。多次调用应幂等。"""
        ...

    async def snapshot(self) -> dict[str, Any]:
        """对 sandbox 当前状态打个轻量快照(用于长任务暂停/恢复)。

        S1 实现:返回 metadata only(create_time、cwd、env);S3 升级真镜像。
        """
        ...


@runtime_checkable
class SandboxProvider(Protocol):
    """Provider 工厂。"""

    name: str

    async def healthy(self) -> bool:
        """非阻塞健康检查 — manager 启动时调一次。"""
        ...

    async def acquire(
        self,
        *,
        task_id: str | None = None,
        wall_clock_budget_s: int = 600,
        max_stdout_bytes: int = 4 * 1024 * 1024,
        env: dict[str, str] | None = None,
    ) -> Sandbox:
        """申请一个新 sandbox。失败抛 SandboxUnavailable。"""
        ...

    async def release(self, sandbox: Sandbox) -> None:
        """释放 sandbox(等同 sandbox.close,但 provider 可做池回收)。"""
        ...


# ─────────────────────────────────────────────────────────────────
# Sandbox 基类 — provider 的 Sandbox 实现可以继承(可选)
# ─────────────────────────────────────────────────────────────────
@dataclass
class _SandboxBase:
    """实现方便利基类 — provider 可继承,提供生命周期模板。"""

    sandbox_id: str
    provider_name: str
    task_id: str | None = None
    created_at: float = field(default_factory=time.monotonic)

    async def __aenter__(self) -> "_SandboxBase":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()  # type: ignore[attr-defined]
