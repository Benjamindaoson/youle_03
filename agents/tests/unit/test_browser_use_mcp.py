"""mcp-browser-use 工具基础测试(ADR-026)。

不真启动浏览器(需 playwright + chromium binary,CI 不一定有);
只测:
  - 输入校验
  - playwright 未装时的 graceful degradation
"""

from __future__ import annotations


from mcp_servers.browser_use.server import (
    click,
    fill,
    navigate,
    wait_for,
)


# ─── 输入校验 ───
async def test_navigate_requires_url() -> None:
    r = await navigate({})
    assert "error" in r
    assert "url is required" in r["error"]


async def test_click_requires_selector() -> None:
    r = await click({})
    assert "error" in r
    assert "selector is required" in r["error"]


async def test_fill_requires_selector_and_value() -> None:
    r1 = await fill({})
    assert "error" in r1
    r2 = await fill({"selector": "#x"})
    assert "error" in r2
    r3 = await fill({"selector": "#x", "value": "ok"})
    # 没装 playwright 也会抛,但消息不同
    assert "error" in r3


async def test_wait_for_requires_selector() -> None:
    r = await wait_for({})
    assert "error" in r
    assert "selector is required" in r["error"]


# ─── playwright 未装时的 graceful 行为 ───
async def test_navigate_graceful_without_playwright(monkeypatch) -> None:
    """模拟 playwright 不在 → navigate 返回 error 而不是崩溃。"""
    import mcp_servers.browser_use.server as srv

    monkeypatch.setattr(srv, "_try_import_playwright", lambda: None)
    # 重置全局 session
    srv._page = srv._browser = srv._context = srv._pw = None  # type: ignore[attr-defined]

    r = await navigate({"url": "https://example.com"})
    assert "error" in r
    assert "Playwright" in r["error"] or "未安装" in r["error"]
