"""E2BSandboxProvider — e2b.dev SaaS sandbox(ADR-025)。

# 状态:适配器骨架
e2b 的 SDK(`e2b-code-interpreter`)未在 pyproject 里 — production 启用时
按需安装(我们故意不写死,免得 dev/CI 多吃 50MB 依赖)。

import 阶段优雅失败:SDK 不在 → `acquire` 抛 `SandboxUnavailable`,
manager 回退到 local provider 或失败响应。

# 接入清单(production)
1. `pip install e2b-code-interpreter` 进 production 镜像
2. 设置 `E2B_API_KEY` 环境变量
3. 改 `SANDBOX_PROVIDER=e2b`

# 风险隔离
e2b 是 SaaS,网络 / 限流 / API 变更都可能挂。所有方法用 try/except 捕获
sdk 异常并转成 ExecResult.error(网络错误时)或 SandboxUnavailable(全挂)。
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

import structlog

from agents._common.sandbox.provider import (
    ExecResult,
    SandboxBudgetExceeded,
    SandboxUnavailable,
    _SandboxBase,
)

log = structlog.get_logger(__name__)


def _try_import_e2b():
    """延迟 import,SDK 不在不会让本模块 import 失败。"""
    try:
        from e2b_code_interpreter import Sandbox as E2BSdkSandbox  # type: ignore
        return E2BSdkSandbox
    except ImportError:
        return None


class E2BSandbox(_SandboxBase):
    def __init__(
        self,
        *,
        sandbox_id: str,
        task_id: str | None,
        sdk_handle: Any,
        wall_clock_budget_s: int,
        max_stdout_bytes: int,
    ) -> None:
        super().__init__(
            sandbox_id=sandbox_id,
            provider_name="e2b",
            task_id=task_id,
        )
        self._sdk = sdk_handle
        self._wall_budget = wall_clock_budget_s
        self._max_stdout = max_stdout_bytes
        self._closed = False
        self._stdout_consumed = 0

    def _check_budget(self) -> None:
        if self._closed:
            raise SandboxBudgetExceeded(f"sandbox {self.sandbox_id} closed")
        elapsed = time.monotonic() - self.created_at
        if elapsed > self._wall_budget:
            raise SandboxBudgetExceeded(
                f"e2b sandbox {self.sandbox_id} wall-clock exceeded"
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
        # e2b SDK 的具体 API 在不同 SDK 版本有差异,这里只放骨架。
        # production 上线前需要按当前 SDK 文档对齐。
        try:
            cap = max_stdout_bytes or (self._max_stdout - self._stdout_consumed)
            started = time.monotonic()
            result = await _maybe_async(
                self._sdk.commands.run, cmd, cwd=cwd or "/home/user", timeout=timeout_s or 60
            )
            duration_ms = int((time.monotonic() - started) * 1000)
            stdout = (getattr(result, "stdout", "") or "")[:cap] if cap else getattr(result, "stdout", "")
            stderr = getattr(result, "stderr", "") or ""
            self._stdout_consumed += len(stdout or "")
            return ExecResult(
                stdout=stdout or "",
                stderr=stderr or "",
                returncode=getattr(result, "exit_code", None),
                duration_ms=duration_ms,
                truncated=cap is not None and len(stdout or "") >= cap,
            )
        except Exception as e:
            log.warning("e2b_sandbox.exec_fail", err=str(e)[:200])
            return ExecResult(error=str(e)[:300])

    async def python(
        self,
        code: str,
        *,
        timeout_s: int | None = None,
        max_stdout_bytes: int | None = None,
    ) -> ExecResult:
        self._check_budget()
        try:
            started = time.monotonic()
            result = await _maybe_async(self._sdk.run_code, code, timeout=timeout_s or 60)
            duration_ms = int((time.monotonic() - started) * 1000)
            logs = getattr(result, "logs", None)
            stdout = "\n".join(getattr(logs, "stdout", []) or [])
            stderr = "\n".join(getattr(logs, "stderr", []) or [])
            cap = max_stdout_bytes or (self._max_stdout - self._stdout_consumed)
            if cap and len(stdout) > cap:
                stdout = stdout[:cap]
            self._stdout_consumed += len(stdout)
            err = getattr(result, "error", None)
            return ExecResult(
                stdout=stdout,
                stderr=stderr or (str(err) if err else ""),
                returncode=0 if err is None else 1,
                duration_ms=duration_ms,
                error=str(err)[:300] if err else None,
            )
        except Exception as e:
            log.warning("e2b_sandbox.python_fail", err=str(e)[:200])
            return ExecResult(error=str(e)[:300])

    async def write_file(self, path: str, content: bytes | str) -> None:
        self._check_budget()
        try:
            data = content.encode("utf-8") if isinstance(content, str) else content
            await _maybe_async(self._sdk.files.write, path, data)
        except Exception as e:
            log.warning("e2b_sandbox.write_fail", path=path, err=str(e)[:200])
            raise

    async def read_file(self, path: str, *, max_bytes: int | None = None) -> bytes:
        self._check_budget()
        try:
            raw = await _maybe_async(self._sdk.files.read, path)
            data = raw if isinstance(raw, bytes) else (raw or "").encode("utf-8")
            if max_bytes is not None and len(data) > max_bytes:
                return data[:max_bytes]
            return data
        except Exception as e:
            log.warning("e2b_sandbox.read_fail", path=path, err=str(e)[:200])
            raise

    async def list_dir(self, path: str = ".") -> list[str]:
        self._check_budget()
        try:
            entries = await _maybe_async(self._sdk.files.list, path)
            return [getattr(e, "name", str(e)) for e in (entries or [])]
        except Exception as e:
            log.warning("e2b_sandbox.list_fail", path=path, err=str(e)[:200])
            return []

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await _maybe_async(self._sdk.kill)
        except Exception as e:
            log.warning("e2b_sandbox.kill_fail", err=str(e)[:200])

    async def snapshot(self) -> dict[str, Any]:
        return {
            "sandbox_id": self.sandbox_id,
            "provider": self.provider_name,
            "task_id": self.task_id,
            "created_at": self.created_at,
            "stdout_consumed": self._stdout_consumed,
            "closed": self._closed,
        }


class E2BSandboxProvider:
    name = "e2b"

    def __init__(self) -> None:
        self._sdk_cls = _try_import_e2b()
        self._api_key = os.getenv("E2B_API_KEY")

    async def healthy(self) -> bool:
        return self._sdk_cls is not None and bool(self._api_key)

    async def acquire(
        self,
        *,
        task_id: str | None = None,
        wall_clock_budget_s: int = 600,
        max_stdout_bytes: int = 4 * 1024 * 1024,
        env: dict[str, str] | None = None,
    ) -> E2BSandbox:
        if self._sdk_cls is None:
            raise SandboxUnavailable(
                "e2b-code-interpreter SDK 未安装。"
                "production 部署需 `pip install e2b-code-interpreter`。"
            )
        if not self._api_key:
            raise SandboxUnavailable("E2B_API_KEY 未设置。")
        try:
            sdk = await _maybe_async(self._sdk_cls.create, api_key=self._api_key)
        except Exception as e:
            raise SandboxUnavailable(f"e2b sandbox create failed: {e}") from e
        sid = "e2b-" + uuid.uuid4().hex[:10]
        log.info("e2b_sandbox.acquired", sandbox_id=sid, task_id=task_id)
        return E2BSandbox(
            sandbox_id=sid,
            task_id=task_id,
            sdk_handle=sdk,
            wall_clock_budget_s=wall_clock_budget_s,
            max_stdout_bytes=max_stdout_bytes,
        )

    async def release(self, sandbox: E2BSandbox) -> None:  # type: ignore[override]
        await sandbox.close()


# ─────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────
async def _maybe_async(fn, *args, **kwargs):
    """e2b SDK 在不同版本有同步/异步两种接口 — 兼容包装。"""
    import inspect

    res = fn(*args, **kwargs)
    if inspect.isawaitable(res):
        return await res
    return res


def make_e2b_provider():
    return E2BSandboxProvider()
