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

    import agents.mcp_servers.code_executor.server as srv  # noqa: E402

    srv._sandbox = None  # type: ignore[attr-defined]
    yield
    srv._sandbox = None  # type: ignore[attr-defined]
    reset_default_manager()


async def test_python_exec_smoke() -> None:
    from agents.mcp_servers.code_executor.server import python_exec

    r = await python_exec({"code": "print(2 + 2)"})
    if r.get("error"):
        pytest.skip(f"python interpreter unavailable: {r['error']}")
    assert r["ok"] is True
    assert "4" in r["stdout"]


async def test_python_exec_missing_code() -> None:
    from agents.mcp_servers.code_executor.server import python_exec

    r = await python_exec({})
    assert "error" in r
    assert "required" in r["error"]


async def test_shell_exec_smoke() -> None:
    from agents.mcp_servers.code_executor.server import shell_exec

    import sys

    cmd = "echo hello-world"
    r = await shell_exec({"cmd": cmd, "timeout_s": 5})
    if r.get("error"):
        pytest.skip(f"shell unavailable: {r['error']}")
    assert "hello-world" in r["stdout"]


async def test_write_then_read_text() -> None:
    from agents.mcp_servers.code_executor.server import read_file, write_file

    w = await write_file({"path": "x.txt", "content": "你好 world"})
    assert w == {"written": True, "path": "x.txt"}
    r = await read_file({"path": "x.txt"})
    assert r["encoding"] == "utf-8"
    assert "你好 world" == r["content"]


async def test_write_then_read_base64() -> None:
    from agents.mcp_servers.code_executor.server import read_file, write_file

    payload = b"\x00\x01\x02\x03"
    w = await write_file(
        {
            "path": "bin",
            "content": base64.b64encode(payload).decode("ascii"),
            "encoding": "base64",
        }
    )
    assert w["written"] is True

    r = await read_file({"path": "bin", "encoding": "base64"})
    assert base64.b64decode(r["content"]) == payload


async def test_read_missing_returns_error() -> None:
    from agents.mcp_servers.code_executor.server import read_file

    r = await read_file({"path": "no-such.txt"})
    assert "error" in r
    assert "not_found" in r["error"]


async def test_list_dir() -> None:
    from agents.mcp_servers.code_executor.server import list_dir, write_file

    await write_file({"path": "a.txt", "content": "1"})
    await write_file({"path": "b.txt", "content": "2"})
    r = await list_dir({"path": "."})
    assert r["count"] >= 2
    assert "a.txt" in r["entries"]
    assert "b.txt" in r["entries"]


async def test_install_disabled_by_default() -> None:
    from agents.mcp_servers.code_executor.server import install_package

    r = await install_package({"name": "pandas"})
    assert "error" in r
    assert "disabled" in r["error"]


async def test_install_whitelist_enforced(monkeypatch) -> None:
    monkeypatch.setenv("CODE_EXECUTOR_ALLOW_PIP", "true")
    # 重新 import 让 module-level 常量重读
    import importlib

    import agents.mcp_servers.code_executor.server as srv

    importlib.reload(srv)

    r = await srv.install_package({"name": "definitely-not-in-whitelist"})
    assert "not in whitelist" in r["error"]
