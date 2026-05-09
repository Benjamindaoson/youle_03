"""Sandbox 抽象 + LocalSandbox 测试(ADR-025)。

只测 local provider — e2b 需 SDK + API key,在 production 环境单独验证。
"""

from __future__ import annotations

import pytest

from agents._common.sandbox import (
    ExecResult,
    Sandbox,
    SandboxBudgetExceeded,
    SandboxManager,
    SandboxProvider,
    SandboxUnavailable,
    get_default_manager,
)
from agents._common.sandbox.provider_local import (
    LocalSandboxProvider,
    make_local_provider,
)


# ─── Provider 接口契约 ───
def test_local_provider_implements_protocol() -> None:
    p = make_local_provider()
    assert isinstance(p, SandboxProvider)
    assert p.name == "local"


async def test_local_provider_healthy(tmp_path) -> None:
    p = LocalSandboxProvider(root=str(tmp_path))
    assert (await p.healthy()) is True


# ─── 生命周期 ───
async def test_acquire_release(tmp_path) -> None:
    p = LocalSandboxProvider(root=str(tmp_path))
    sb = await p.acquire(task_id="t-1")
    assert isinstance(sb, Sandbox)
    assert sb.task_id == "t-1"
    assert sb.provider_name == "local"
    await p.release(sb)


async def test_session_context_manager(tmp_path) -> None:
    mgr = SandboxManager(provider=LocalSandboxProvider(root=str(tmp_path)))
    async with mgr.session(task_id="t-1") as sb:
        assert sb.task_id == "t-1"
    # 退出后 sandbox 已 close,目录已删
    snap = await sb.snapshot()
    assert snap["closed"] is True


# ─── exec / python ───
async def test_python_executes(tmp_path) -> None:
    mgr = SandboxManager(provider=LocalSandboxProvider(root=str(tmp_path)))
    async with mgr.session() as sb:
        r = await sb.python("print(1 + 1)")
        assert isinstance(r, ExecResult)
        if r.error:
            pytest.skip(f"python interpreter unavailable in this env: {r.error}")
        assert r.ok()
        assert "2" in r.stdout


async def test_exec_timeout(tmp_path) -> None:
    mgr = SandboxManager(provider=LocalSandboxProvider(root=str(tmp_path)))
    async with mgr.session() as sb:
        # Windows 没有 sleep,用 ping;Unix 用 sleep
        import sys
        cmd = "ping -n 5 127.0.0.1 >NUL" if sys.platform == "win32" else "sleep 5"
        r = await sb.exec(cmd, timeout_s=1)
        # 不抛 — 而是返回 timed_out=True
        assert r.timed_out is True
        assert r.returncode is None


async def test_python_captures_stdout(tmp_path) -> None:
    mgr = SandboxManager(provider=LocalSandboxProvider(root=str(tmp_path)))
    async with mgr.session() as sb:
        r = await sb.python(
            "for i in range(3): print(f'line {i}')",
            timeout_s=10,
        )
        if r.error:
            pytest.skip(f"python interpreter unavailable: {r.error}")
        assert "line 0" in r.stdout
        assert "line 2" in r.stdout


# ─── 文件 IO ───
async def test_write_read_file(tmp_path) -> None:
    mgr = SandboxManager(provider=LocalSandboxProvider(root=str(tmp_path)))
    async with mgr.session() as sb:
        await sb.write_file("data.txt", "hello sandbox")
        body = await sb.read_file("data.txt")
        assert body.decode("utf-8") == "hello sandbox"


async def test_write_binary(tmp_path) -> None:
    mgr = SandboxManager(provider=LocalSandboxProvider(root=str(tmp_path)))
    async with mgr.session() as sb:
        payload = b"\x00\x01\x02\x03"
        await sb.write_file("blob.bin", payload)
        out = await sb.read_file("blob.bin")
        assert out == payload


async def test_list_dir(tmp_path) -> None:
    mgr = SandboxManager(provider=LocalSandboxProvider(root=str(tmp_path)))
    async with mgr.session() as sb:
        await sb.write_file("a.txt", "1")
        await sb.write_file("b.txt", "2")
        names = await sb.list_dir(".")
        assert "a.txt" in names
        assert "b.txt" in names


async def test_read_max_bytes(tmp_path) -> None:
    mgr = SandboxManager(provider=LocalSandboxProvider(root=str(tmp_path)))
    async with mgr.session() as sb:
        await sb.write_file("big.txt", "x" * 10000)
        r = await sb.read_file("big.txt", max_bytes=100)
        assert len(r) == 100


# ─── 预算 / 错误 ───
async def test_close_idempotent(tmp_path) -> None:
    p = LocalSandboxProvider(root=str(tmp_path))
    sb = await p.acquire()
    await sb.close()
    await sb.close()  # 不抛


async def test_exec_after_close_raises_budget(tmp_path) -> None:
    p = LocalSandboxProvider(root=str(tmp_path))
    sb = await p.acquire()
    await sb.close()
    with pytest.raises(SandboxBudgetExceeded):
        await sb.exec("echo x", timeout_s=2)


async def test_snapshot_metadata(tmp_path) -> None:
    p = LocalSandboxProvider(root=str(tmp_path))
    sb = await p.acquire(task_id="abc")
    snap = await sb.snapshot()
    assert snap["sandbox_id"] == sb.sandbox_id
    assert snap["provider"] == "local"
    assert snap["task_id"] == "abc"
    assert snap["closed"] is False
    await p.release(sb)
    snap2 = await sb.snapshot()
    assert snap2["closed"] is True


# ─── e2b 不可用时优雅 fallback ───
async def test_e2b_provider_missing_sdk_raises_unavailable(monkeypatch) -> None:
    """SDK 没装时,acquire 抛 SandboxUnavailable 而不是其他错误。"""
    from agents._common.sandbox.provider_e2b import E2BSandboxProvider

    p = E2BSandboxProvider()
    # 强制 SDK = None
    p._sdk_cls = None  # type: ignore[attr-defined]
    with pytest.raises(SandboxUnavailable):
        await p.acquire(task_id="t-1")


async def test_manager_default_is_local(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SANDBOX_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_SANDBOX_ROOT", str(tmp_path))
    from agents._common.sandbox.manager import reset_default_manager

    reset_default_manager()
    mgr = get_default_manager()
    assert mgr.provider_name == "local"
    reset_default_manager()


async def test_manager_unknown_provider_falls_back_local(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SANDBOX_PROVIDER", "imaginary")
    monkeypatch.setenv("LOCAL_SANDBOX_ROOT", str(tmp_path))
    from agents._common.sandbox.manager import reset_default_manager

    reset_default_manager()
    mgr = get_default_manager()
    assert mgr.provider_name == "local"  # silent fallback
    reset_default_manager()
