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
**S1 单 sandbox 池**:server 启动时获取一个 sandbox,所有 task 共用。
**这显然不对** — production 必须 per-task sandbox。本文件留 TODO,
S2 改造点是 `_resolve_sandbox(task_id)`(从 header 读 task_id,做 task→sandbox 映射)。
"""

from __future__ import annotations

import asyncio
import base64
import os
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
ALLOW_PIP_INSTALL = os.getenv("CODE_EXECUTOR_ALLOW_PIP", "false").lower() in {"1", "true", "yes"}
PIP_PACKAGE_WHITELIST = {
    p.strip()
    for p in os.getenv(
        "CODE_EXECUTOR_PIP_WHITELIST",
        "pandas,numpy,pillow,requests,beautifulsoup4,lxml,openpyxl,python-dateutil",
    ).split(",")
    if p.strip()
}


# ─── Session(S1 共享单 sandbox)───
_sandbox: Sandbox | None = None
_lock = asyncio.Lock()


async def _resolve_sandbox() -> Sandbox:
    """S1 实现:进程级单 sandbox。

    S2 改造:从 task_id / 用户身份解析,per-task sandbox 池。
    """
    global _sandbox
    if _sandbox is not None:
        return _sandbox
    mgr = get_default_manager()
    try:
        _sandbox = await mgr.acquire(task_id="code-executor-shared")
    except SandboxUnavailable as e:
        raise RuntimeError(f"sandbox unavailable: {e}") from e
    return _sandbox


# ─── 工具实现 ───
async def python_exec(arguments: dict[str, Any]) -> dict[str, Any]:
    code = arguments.get("code")
    if not isinstance(code, str) or not code.strip():
        return {"error": "code is required"}
    timeout_s = int(arguments.get("timeout_s") or DEFAULT_TIMEOUT_S)
    max_stdout_bytes = arguments.get("max_stdout_bytes")
    async with _lock:
        try:
            sb = await _resolve_sandbox()
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
    cwd = arguments.get("cwd")
    timeout_s = int(arguments.get("timeout_s") or DEFAULT_TIMEOUT_S)
    async with _lock:
        try:
            sb = await _resolve_sandbox()
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
    async with _lock:
        try:
            sb = await _resolve_sandbox()
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
    async with _lock:
        try:
            sb = await _resolve_sandbox()
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
    async with _lock:
        try:
            sb = await _resolve_sandbox()
            names = await sb.list_dir(path)
            return {"path": path, "entries": names, "count": len(names)}
        except Exception as e:
            return {"error": str(e)[:300]}


async def install_package(arguments: dict[str, Any]) -> dict[str, Any]:
    name = str(arguments.get("name") or "").strip()
    if not name:
        return {"error": "name is required"}
    if not ALLOW_PIP_INSTALL:
        return {"error": "pip install disabled by CODE_EXECUTOR_ALLOW_PIP=false"}
    if name not in PIP_PACKAGE_WHITELIST:
        return {
            "error": f"package {name!r} not in whitelist",
            "whitelist": sorted(PIP_PACKAGE_WHITELIST),
        }
    async with _lock:
        try:
            sb = await _resolve_sandbox()
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
}


app = make_app(server_name="code-executor", tools=TOOLS)


if __name__ == "__main__":
    import uvicorn

    # ⚠️ V1 部署约束:**单副本(concurrency=1)** — 共享 sandbox 实例,
    # 多 worker 同时操作会串档。S2 改 per-task sandbox 后才能横向扩。
    port = int(os.getenv("PORT", "7009"))
    uvicorn.run(app, host="0.0.0.0", port=port, workers=1)
