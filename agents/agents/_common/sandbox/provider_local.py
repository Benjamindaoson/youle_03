"""LocalSandboxProvider — subprocess + tempdir(ADR-025)。

**警告:本 provider 没有真实隔离**(没有 microVM / 容器),只是用 tempdir 做
工作目录隔离 + subprocess 跑命令 + 超时控制。**仅供 dev / CI 用**。

production 应当用 `provider_e2b.py` 或 S3 的 `provider_firecracker.py`。
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import structlog

from agents._common.sandbox.provider import (
    ExecResult,
    SandboxBudgetExceeded,
    SandboxProvider,
    SandboxUnavailable,
    _SandboxBase,
)

log = structlog.get_logger(__name__)

LOCAL_SANDBOX_ROOT = os.getenv(
    "LOCAL_SANDBOX_ROOT", str(Path(tempfile.gettempdir()) / "youle-sandbox")
)
PYTHON_EXE = os.getenv("LOCAL_SANDBOX_PYTHON", "python")


class LocalSandbox(_SandboxBase):
    def __init__(
        self,
        *,
        sandbox_id: str,
        task_id: str | None,
        cwd: Path,
        wall_clock_budget_s: int,
        max_stdout_bytes: int,
        env: dict[str, str] | None,
    ) -> None:
        super().__init__(
            sandbox_id=sandbox_id,
            provider_name="local",
            task_id=task_id,
        )
        self._cwd: Path = cwd
        self._wall_budget = wall_clock_budget_s
        self._max_stdout = max_stdout_bytes
        self._env = dict(env or {})
        self._closed = False
        self._stdout_consumed = 0
        self._exec_count = 0

    def _check_budget(self) -> None:
        if self._closed:
            raise SandboxBudgetExceeded(f"sandbox {self.sandbox_id} closed")
        elapsed = time.monotonic() - self.created_at
        if elapsed > self._wall_budget:
            raise SandboxBudgetExceeded(
                f"sandbox {self.sandbox_id} wall-clock {elapsed:.0f}s > {self._wall_budget}s"
            )

    async def exec(
        self,
        cmd: str,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_s: int | None = None,
        max_stdout_bytes: int | None = None,
    ) -> ExecResult:
        self._check_budget()
        self._exec_count += 1
        cap = max_stdout_bytes or (self._max_stdout - self._stdout_consumed)
        cap = max(0, cap)
        timeout = timeout_s or 60

        full_env = {**os.environ, **self._env, **(env or {})}
        run_cwd = str(self._cwd / cwd) if cwd else str(self._cwd)
        started = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=run_cwd,
                env=full_env,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ExecResult(
                    stdout="",
                    stderr=f"timeout after {timeout}s",
                    returncode=None,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    timed_out=True,
                )
            duration_ms = int((time.monotonic() - started) * 1000)
            stdout = stdout_b.decode("utf-8", errors="replace")
            stderr = stderr_b.decode("utf-8", errors="replace")
            truncated = False
            if cap and len(stdout) > cap:
                stdout = stdout[:cap]
                truncated = True
            self._stdout_consumed += len(stdout)
            return ExecResult(
                stdout=stdout,
                stderr=stderr,
                returncode=proc.returncode,
                duration_ms=duration_ms,
                truncated=truncated,
            )
        except Exception as e:  # subprocess 自身故障
            log.warning("local_sandbox.exec_fail", err=str(e)[:200], cmd=cmd[:120])
            return ExecResult(error=str(e)[:300])

    async def python(
        self,
        code: str,
        *,
        timeout_s: int | None = None,
        max_stdout_bytes: int | None = None,
    ) -> ExecResult:
        # 落到 sandbox cwd 下临时文件,避免 shell 转义噩梦
        script_name = f"_youle_{uuid.uuid4().hex[:8]}.py"
        script_path = self._cwd / script_name
        script_path.write_text(code, encoding="utf-8")
        try:
            return await self.exec(
                f'"{PYTHON_EXE}" "{script_name}"',
                timeout_s=timeout_s,
                max_stdout_bytes=max_stdout_bytes,
            )
        finally:
            try:
                script_path.unlink(missing_ok=True)
            except OSError:
                pass

    async def write_file(self, path: str, content: bytes | str) -> None:
        target = self._cwd / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            target.write_text(content, encoding="utf-8")
        else:
            target.write_bytes(content)

    async def read_file(self, path: str, *, max_bytes: int | None = None) -> bytes:
        target = self._cwd / path
        if not target.exists():
            raise FileNotFoundError(str(target))
        data = target.read_bytes()
        if max_bytes is not None and len(data) > max_bytes:
            return data[:max_bytes]
        return data

    async def list_dir(self, path: str = ".") -> list[str]:
        target = self._cwd / path
        if not target.exists() or not target.is_dir():
            return []
        return sorted(p.name for p in target.iterdir())

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            shutil.rmtree(self._cwd, ignore_errors=True)
        except Exception as e:
            log.warning("local_sandbox.cleanup_fail", err=str(e)[:200], cwd=str(self._cwd))

    async def snapshot(self) -> dict[str, Any]:
        return {
            "sandbox_id": self.sandbox_id,
            "provider": self.provider_name,
            "task_id": self.task_id,
            "cwd": str(self._cwd),
            "created_at": self.created_at,
            "exec_count": self._exec_count,
            "stdout_consumed": self._stdout_consumed,
            "closed": self._closed,
        }


class LocalSandboxProvider:
    """符合 SandboxProvider Protocol 的本地实现。"""

    name = "local"

    def __init__(self, root: str | None = None) -> None:
        self._root = Path(root or LOCAL_SANDBOX_ROOT)

    async def healthy(self) -> bool:
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            return self._root.exists()
        except OSError:
            return False

    async def acquire(
        self,
        *,
        task_id: str | None = None,
        wall_clock_budget_s: int = 600,
        max_stdout_bytes: int = 4 * 1024 * 1024,
        env: dict[str, str] | None = None,
    ) -> LocalSandbox:
        _PROD_ENVS = frozenset({"production", "prod"})
        if os.getenv("APP_ENV", "").lower() in _PROD_ENVS:
            raise RuntimeError(
                "LocalSandboxProvider is not permitted in production "
                f"(APP_ENV={os.getenv('APP_ENV')}). "
                "Set SANDBOX_PROVIDER=e2b to use the isolated microVM sandbox."
            )
        if not await self.healthy():
            raise SandboxUnavailable(
                f"LOCAL_SANDBOX_ROOT={self._root} unwritable"
            )
        sid = "local-" + uuid.uuid4().hex[:10]
        cwd = self._root / sid
        cwd.mkdir(parents=True, exist_ok=False)
        log.info(
            "local_sandbox.acquired",
            sandbox_id=sid,
            task_id=task_id,
            cwd=str(cwd),
        )
        return LocalSandbox(
            sandbox_id=sid,
            task_id=task_id,
            cwd=cwd,
            wall_clock_budget_s=wall_clock_budget_s,
            max_stdout_bytes=max_stdout_bytes,
            env=env,
        )

    async def release(self, sandbox: LocalSandbox) -> None:  # type: ignore[override]
        await sandbox.close()


# 仅暴露给 manager 工厂使用
def make_local_provider() -> SandboxProvider:
    return LocalSandboxProvider()
