"""mcp-code-executor:在 Sandbox 内执行 Python / shell + 文件 I/O(ADR-026)。

# 工具集
  - python_exec(code, timeout_s?, max_stdout_bytes?)
  - shell_exec(cmd, cwd?, timeout_s?)
  - write_file(path, content [text or base64], encoding?)
  - read_file(path, max_bytes?, encoding?)
  - list_dir(path?)
  - install_package(name)              # pip install — production 应 deny 或限白名单

# 实现
转发到 `agents._common.sandbox.SandboxManager`。SANDBOX_PROVIDER=local 时
使用 tempdir + subprocess(dev),production 改 e2b 即可零代码切换。

# 隔离边界
本 MCP server **不直接执行用户代码**;它只是把请求转发到 sandbox。
真正的隔离由 sandbox provider 提供(local 弱 / e2b 强)。

# Session
每个工具调用必须携带 `task_id`。同一任务复用 sandbox，不同任务严格隔离；
会话数有上限，并可用 `close_session` 主动释放，避免长期占用资源。
"""

from __future__ import annotations

import asyncio
import base64
import os
from collections import OrderedDict
from typing import Any

import structlog

from agents._common.sandbox import (
    Sandbox,
    SandboxBudgetExceeded,
    SandboxUnavailable,
    get_default_manager,
)
from mcp_servers._shared.http_app import make_app

log = structlog.get_logger(__name__)

DEFAULT_TIMEOUT_S = int(os.getenv("CODE_EXECUTOR_DEFAULT_TIMEOUT_S", "60"))
MAX_SESSIONS = max(1, int(os.getenv("CODE_EXECUTOR_MAX_SESSIONS", "4")))
ALLOW_PIP_INSTALL = os.getenv("CODE_EXECUTOR_ALLOW_PIP", "false").lower() in {"1", "true", "yes"}
PIP_PACKAGE_WHITELIST = {
    p.strip()
    for p in os.getenv(
        "CODE_EXECUTOR_PIP_WHITELIST",
        "pandas,numpy,pillow,requests,beautifulsoup4,lxml,openpyxl,python-dateutil",
    ).split(",")
    if p.strip()
}


# ─── Bounded per-task sessions ───
_sandboxes: OrderedDict[str, Sandbox] = OrderedDict()
_lock = asyncio.Lock()


def _require_task_id(arguments: dict[str, Any]) -> str:
    task_id = str(arguments.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("task_id is required")
    return task_id


async def _resolve_sandbox(task_id: str) -> Sandbox:
    """Return the isolated sandbox assigned to this task."""
    sandbox = _sandboxes.get(task_id)
    if sandbox is not None:
        _sandboxes.move_to_end(task_id)
        return sandbox
    mgr = get_default_manager()
    try:
        if len(_sandboxes) >= MAX_SESSIONS:
            _, expired = _sandboxes.popitem(last=False)
            await mgr.release(expired)
        sandbox = await mgr.acquire(task_id=task_id)
    except SandboxUnavailable as e:
        raise RuntimeError(f"sandbox unavailable: {e}") from e
    _sandboxes[task_id] = sandbox
    return sandbox


async def close_session(arguments: dict[str, Any]) -> dict[str, Any]:
    """Release a task sandbox and all temporary state stored in it."""
    try:
        task_id = _require_task_id(arguments)
    except ValueError as exc:
        return {"error": str(exc)}
    async with _lock:
        sandbox = _sandboxes.pop(task_id, None)
        if sandbox is None:
            return {"closed": False, "task_id": task_id}
        await get_default_manager().release(sandbox)
        return {"closed": True, "task_id": task_id}


# ─── 工具实现 ───
async def python_exec(arguments: dict[str, Any]) -> dict[str, Any]:
    code = arguments.get("code")
    if not isinstance(code, str) or not code.strip():
        return {"error": "code is required"}
    try:
        task_id = _require_task_id(arguments)
    except ValueError as exc:
        return {"error": str(exc)}
    timeout_s = int(arguments.get("timeout_s") or DEFAULT_TIMEOUT_S)
    max_stdout_bytes = arguments.get("max_stdout_bytes")
    async with _lock:
        try:
            sb = await _resolve_sandbox(task_id)
            r = await sb.python(
                code,
                timeout_s=timeout_s,
                max_stdout_bytes=int(max_stdout_bytes) if max_stdout_bytes else None,
            )
            return {
                "stdout": r.stdout,
                "stderr": r.stderr,
                "returncode": r.returncode,
                "duration_ms": r.duration_ms,
                "truncated": r.truncated,
                "timed_out": r.timed_out,
                "error": r.error,
                "ok": r.ok(),
            }
        except SandboxBudgetExceeded as e:
            return {"error": f"budget_exceeded: {e}"}
        except Exception as e:
            log.warning("code_executor.python_fail", err=str(e)[:200])
            return {"error": str(e)[:300]}


async def shell_exec(arguments: dict[str, Any]) -> dict[str, Any]:
    cmd = arguments.get("cmd")
    if not isinstance(cmd, str) or not cmd.strip():
        return {"error": "cmd is required"}
    try:
        task_id = _require_task_id(arguments)
    except ValueError as exc:
        return {"error": str(exc)}
    cwd = arguments.get("cwd")
    timeout_s = int(arguments.get("timeout_s") or DEFAULT_TIMEOUT_S)
    async with _lock:
        try:
            sb = await _resolve_sandbox(task_id)
            r = await sb.exec(cmd, cwd=cwd, timeout_s=timeout_s)
            return {
                "stdout": r.stdout,
                "stderr": r.stderr,
                "returncode": r.returncode,
                "duration_ms": r.duration_ms,
                "truncated": r.truncated,
                "timed_out": r.timed_out,
                "error": r.error,
                "ok": r.ok(),
            }
        except SandboxBudgetExceeded as e:
            return {"error": f"budget_exceeded: {e}"}
        except Exception as e:
            log.warning("code_executor.shell_fail", err=str(e)[:200])
            return {"error": str(e)[:300]}


async def write_file(arguments: dict[str, Any]) -> dict[str, Any]:
    path = str(arguments.get("path") or "").strip()
    content = arguments.get("content")
    encoding = str(arguments.get("encoding") or "utf-8").lower()
    if not path or content is None:
        return {"error": "path and content are required"}
    try:
        task_id = _require_task_id(arguments)
    except ValueError as exc:
        return {"error": str(exc)}
    async with _lock:
        try:
            sb = await _resolve_sandbox(task_id)
            if encoding == "base64":
                data: bytes | str = base64.b64decode(str(content))
            else:
                data = str(content)
            await sb.write_file(path, data)
            return {"written": True, "path": path}
        except Exception as e:
            return {"error": str(e)[:300]}


async def read_file(arguments: dict[str, Any]) -> dict[str, Any]:
    path = str(arguments.get("path") or "").strip()
    max_bytes = arguments.get("max_bytes")
    encoding = str(arguments.get("encoding") or "utf-8").lower()
    if not path:
        return {"error": "path is required"}
    try:
        task_id = _require_task_id(arguments)
    except ValueError as exc:
        return {"error": str(exc)}
    async with _lock:
        try:
            sb = await _resolve_sandbox(task_id)
            data = await sb.read_file(
                path,
                max_bytes=int(max_bytes) if max_bytes else None,
            )
            if encoding == "base64":
                return {"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"}
            try:
                return {"content": data.decode(encoding), "encoding": encoding}
            except UnicodeDecodeError:
                return {
                    "content": base64.b64encode(data).decode("ascii"),
                    "encoding": "base64",
                    "note": "binary fallback (utf-8 decode failed)",
                }
        except FileNotFoundError as e:
            return {"error": f"not_found: {e}"}
        except Exception as e:
            return {"error": str(e)[:300]}


async def list_dir(arguments: dict[str, Any]) -> dict[str, Any]:
    path = str(arguments.get("path") or ".")
    try:
        task_id = _require_task_id(arguments)
    except ValueError as exc:
        return {"error": str(exc)}
    async with _lock:
        try:
            sb = await _resolve_sandbox(task_id)
            names = await sb.list_dir(path)
            return {"path": path, "entries": names, "count": len(names)}
        except Exception as e:
            return {"error": str(e)[:300]}


async def install_package(arguments: dict[str, Any]) -> dict[str, Any]:
    name = str(arguments.get("name") or "").strip()
    if not name:
        return {"error": "name is required"}
    try:
        task_id = _require_task_id(arguments)
    except ValueError as exc:
        return {"error": str(exc)}
    if not ALLOW_PIP_INSTALL:
        return {"error": "pip install disabled by CODE_EXECUTOR_ALLOW_PIP=false"}
    if name not in PIP_PACKAGE_WHITELIST:
        return {
            "error": f"package {name!r} not in whitelist",
            "whitelist": sorted(PIP_PACKAGE_WHITELIST),
        }
    async with _lock:
        try:
            sb = await _resolve_sandbox(task_id)
            r = await sb.exec(f"pip install --quiet {name}", timeout_s=120)
            return {
                "package": name,
                "installed": r.ok(),
                "stdout": r.stdout[-1000:],
                "stderr": r.stderr[-1000:],
                "returncode": r.returncode,
            }
        except Exception as e:
            return {"error": str(e)[:300]}


TOOLS = {
    "python_exec": python_exec,
    "shell_exec": shell_exec,
    "write_file": write_file,
    "read_file": read_file,
    "list_dir": list_dir,
    "install_package": install_package,
    "close_session": close_session,
}


app = make_app(server_name="code-executor", tools=TOOLS)


if __name__ == "__main__":
    import uvicorn

    # One worker keeps the bounded in-memory task-to-sandbox mapping coherent.
    port = int(os.getenv("PORT", "7009"))
    uvicorn.run(app, host="0.0.0.0", port=port, workers=1)
