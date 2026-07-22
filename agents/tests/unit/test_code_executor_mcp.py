"""mcp-code-executor 工具测试(ADR-026)。

复用 LocalSandboxProvider — 单测无需启 e2b。
"""

from __future__ import annotations

import base64

import pytest


@pytest.fixture(autouse=True)
def reset_sandbox(monkeypatch, tmp_path):
    """每个测试用 fresh tmp_path 作 sandbox 根。"""
    monkeypatch.setenv("SANDBOX_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_SANDBOX_ROOT", str(tmp_path))

    # reset 单例 manager + code_executor 的共享 sandbox
    from agents._common.sandbox.manager import reset_default_manager

    reset_default_manager()

    import mcp_servers.code_executor.server as srv  # noqa: E402

    srv._sandboxes.clear()  # type: ignore[attr-defined]
    yield
    srv._sandboxes.clear()  # type: ignore[attr-defined]
    reset_default_manager()


async def test_python_exec_smoke() -> None:
    from mcp_servers.code_executor.server import python_exec

    r = await python_exec({"task_id": "task-1", "code": "print(2 + 2)"})
    if r.get("error"):
        pytest.skip(f"python interpreter unavailable: {r['error']}")
    assert r["ok"] is True
    assert "4" in r["stdout"]


async def test_python_exec_missing_code() -> None:
    from mcp_servers.code_executor.server import python_exec

    r = await python_exec({})
    assert "error" in r
    assert "required" in r["error"]


async def test_python_exec_requires_task_id() -> None:
    from mcp_servers.code_executor.server import python_exec

    r = await python_exec({"code": "print(1)"})
    assert r == {"error": "task_id is required"}


async def test_shell_exec_smoke() -> None:
    from mcp_servers.code_executor.server import shell_exec


    cmd = "echo hello-world"
    r = await shell_exec({"task_id": "task-1", "cmd": cmd, "timeout_s": 5})
    if r.get("error"):
        pytest.skip(f"shell unavailable: {r['error']}")
    assert "hello-world" in r["stdout"]


async def test_write_then_read_text() -> None:
    from mcp_servers.code_executor.server import read_file, write_file

    w = await write_file({"task_id": "task-1", "path": "x.txt", "content": "你好 world"})
    assert w == {"written": True, "path": "x.txt"}
    r = await read_file({"task_id": "task-1", "path": "x.txt"})
    assert r["encoding"] == "utf-8"
    assert "你好 world" == r["content"]


async def test_write_then_read_base64() -> None:
    from mcp_servers.code_executor.server import read_file, write_file

    payload = b"\x00\x01\x02\x03"
    w = await write_file(
        {
            "task_id": "task-1",
            "path": "bin",
            "content": base64.b64encode(payload).decode("ascii"),
            "encoding": "base64",
        }
    )
    assert w["written"] is True

    r = await read_file({"task_id": "task-1", "path": "bin", "encoding": "base64"})
    assert base64.b64decode(r["content"]) == payload


async def test_read_missing_returns_error() -> None:
    from mcp_servers.code_executor.server import read_file

    r = await read_file({"task_id": "task-1", "path": "no-such.txt"})
    assert "error" in r
    assert "not_found" in r["error"]


async def test_list_dir() -> None:
    from mcp_servers.code_executor.server import list_dir, write_file

    await write_file({"task_id": "task-1", "path": "a.txt", "content": "1"})
    await write_file({"task_id": "task-1", "path": "b.txt", "content": "2"})
    r = await list_dir({"task_id": "task-1", "path": "."})
    assert r["count"] >= 2
    assert "a.txt" in r["entries"]
    assert "b.txt" in r["entries"]


async def test_install_disabled_by_default() -> None:
    from mcp_servers.code_executor.server import install_package

    r = await install_package({"task_id": "task-1", "name": "pandas"})
    assert "error" in r
    assert "disabled" in r["error"]


async def test_install_whitelist_enforced(monkeypatch) -> None:
    monkeypatch.setenv("CODE_EXECUTOR_ALLOW_PIP", "true")
    # 重新 import 让 module-level 常量重读
    import importlib

    import mcp_servers.code_executor.server as srv

    importlib.reload(srv)

    r = await srv.install_package({"task_id": "task-1", "name": "definitely-not-in-whitelist"})
    assert "not in whitelist" in r["error"]


async def test_task_sandboxes_are_isolated() -> None:
    from mcp_servers.code_executor.server import read_file, write_file

    await write_file({"task_id": "task-a", "path": "private.txt", "content": "a"})
    r = await read_file({"task_id": "task-b", "path": "private.txt"})
    assert "not_found" in r["error"]


async def test_close_session_releases_task_state() -> None:
    from mcp_servers.code_executor.server import close_session, read_file, write_file

    await write_file({"task_id": "task-a", "path": "x.txt", "content": "a"})
    assert await close_session({"task_id": "task-a"}) == {
        "closed": True,
        "task_id": "task-a",
    }
    r = await read_file({"task_id": "task-a", "path": "x.txt"})
    assert "not_found" in r["error"]
