"""mcp-browser-use:Playwright 驱动浏览器自动化(ADR-026)。

# 工具集(S1 最小集合)
  - navigate(url, wait_until?)
  - screenshot(full_page?)
  - extract_text(selector?)            # 提取页面文本
  - extract_links()                    # 提取所有 <a href>
  - click(selector, timeout_ms?)
  - fill(selector, value, timeout_ms?)
  - wait_for(selector, timeout_ms?)
  - close()                            # 显式关闭当前 session

# Session 模型
进程级单 session(`_browser` / `_page` 全局)。session 跨多次工具调用保持
登录态 / cookies / 当前页面。**production 多任务并发时**应 per-task session,
那是 S2 改造点(配合 ADR-025 sandbox 把 browser 跑在 sandbox 里)。

# Graceful
Playwright 未装(`playwright` 不在依赖里) → 工具返回 `{"error": "..."}`,
**不让 server 启动失败**。production 部署清单加 `pip install playwright`
+ `playwright install chromium`。
"""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import os
import urllib.parse
from typing import Any

import structlog

from mcp_servers._shared.http_app import make_app

log = structlog.get_logger(__name__)

BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "true").lower() in {"1", "true", "yes"}
BROWSER_TIMEOUT_MS = int(os.getenv("BROWSER_DEFAULT_TIMEOUT_MS", "15000"))
BROWSER_USER_AGENT = os.getenv(
    "BROWSER_USER_AGENT",
    "Mozilla/5.0 (compatible; haoleAgent/1.0)",
)

# ─── SSRF 防护 (ADR-026 S1 补丁) ───
# 阻止访问内网/回环地址,防止 LLM 诱导 Agent 访问内部服务
_SSRF_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),     # loopback
    ipaddress.ip_network("10.0.0.0/8"),      # RFC1918 私有
    ipaddress.ip_network("172.16.0.0/12"),   # RFC1918 私有
    ipaddress.ip_network("192.168.0.0/16"),  # RFC1918 私有
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / AWS metadata
    ipaddress.ip_network("0.0.0.0/8"),       # this-network
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
]


async def _check_ssrf(url: str) -> str | None:
    """返回拦截原因字符串,或 None(允许通过)。"""
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return "invalid URL"
    if parsed.scheme not in ("http", "https"):
        return f"scheme '{parsed.scheme}' not allowed; use http or https"
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return "missing hostname"
    # 直接是 IP 地址则立即判断
    try:
        addr = ipaddress.ip_address(hostname)
        if any(addr in net for net in _SSRF_BLOCKED_NETWORKS):
            return f"blocked internal IP: {hostname}"
    except ValueError:
        pass  # 是域名,走 DNS 解析
    # DNS 解析后对每个 IP 判断
    try:
        loop = asyncio.get_event_loop()
        addr_infos = await loop.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in addr_infos:
            ip_str = sockaddr[0]
            try:
                resolved = ipaddress.ip_address(ip_str)
                if any(resolved in net for net in _SSRF_BLOCKED_NETWORKS):
                    return f"blocked: '{hostname}' resolves to internal address {ip_str}"
            except ValueError:
                pass
    except OSError:
        pass  # DNS 失败,交由浏览器自然超时
    return None


# ─── 全局 session(S1) ───
_pw = None
_browser = None
_context = None
_page = None
_lock = asyncio.Lock()


def _try_import_playwright():
    try:
        from playwright.async_api import async_playwright  # type: ignore
        return async_playwright
    except ImportError:
        return None


async def _ensure_session():
    global _pw, _browser, _context, _page
    if _page is not None:
        return _page
    fn = _try_import_playwright()
    if fn is None:
        raise RuntimeError(
            "Playwright 未安装。production 部署需 `pip install playwright` "
            "+ `playwright install chromium`。"
        )
    if _pw is None:
        _pw = await fn().start()
    if _browser is None:
        _browser = await _pw.chromium.launch(headless=BROWSER_HEADLESS)
    if _context is None:
        _context = await _browser.new_context(user_agent=BROWSER_USER_AGENT)
    if _page is None:
        _page = await _context.new_page()
    return _page


async def _close_session() -> None:
    global _pw, _browser, _context, _page
    try:
        if _page is not None:
            await _page.close()
        if _context is not None:
            await _context.close()
        if _browser is not None:
            await _browser.close()
        if _pw is not None:
            await _pw.stop()
    except Exception as e:
        log.warning("browser_use.close_fail", err=str(e)[:200])
    finally:
        _pw = _browser = _context = _page = None


# ─── 工具实现 ───
async def navigate(arguments: dict[str, Any]) -> dict[str, Any]:
    url = str(arguments.get("url") or "").strip()
    wait_until = str(arguments.get("wait_until") or "load")
    timeout_ms = int(arguments.get("timeout_ms") or BROWSER_TIMEOUT_MS)
    if not url:
        return {"error": "url is required"}
    ssrf_err = await _check_ssrf(url)
    if ssrf_err:
        log.warning("browser_use.ssrf_blocked", url=url, reason=ssrf_err)
        return {"error": f"URL blocked by security policy: {ssrf_err}"}
    async with _lock:
        try:
            page = await _ensure_session()
            resp = await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            return {
                "url": page.url,
                "title": await page.title(),
                "status": resp.status if resp else None,
            }
        except Exception as e:
            log.warning("browser_use.navigate_fail", url=url, err=str(e)[:200])
            return {"error": str(e)[:300]}


async def screenshot(arguments: dict[str, Any]) -> dict[str, Any]:
    full_page = bool(arguments.get("full_page", False))
    async with _lock:
        try:
            page = await _ensure_session()
            png = await page.screenshot(full_page=full_page, type="png")
            return {
                "format": "png",
                "size_bytes": len(png),
                "base64": base64.b64encode(png).decode("ascii"),
            }
        except Exception as e:
            return {"error": str(e)[:300]}


async def extract_text(arguments: dict[str, Any]) -> dict[str, Any]:
    selector = arguments.get("selector")
    max_chars = int(arguments.get("max_chars") or 50_000)
    async with _lock:
        try:
            page = await _ensure_session()
            if selector:
                element = await page.query_selector(str(selector))
                if element is None:
                    return {"text": "", "found": False}
                text = (await element.text_content()) or ""
            else:
                text = await page.evaluate("() => document.body.innerText")
            text = text or ""
            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]
            return {"text": text, "found": True, "truncated": truncated}
        except Exception as e:
            return {"error": str(e)[:300]}


async def extract_links(arguments: dict[str, Any]) -> dict[str, Any]:
    max_links = int(arguments.get("max_links") or 200)
    async with _lock:
        try:
            page = await _ensure_session()
            hrefs = await page.evaluate(
                "() => Array.from(document.querySelectorAll('a[href]')).map(a => "
                "({href: a.href, text: (a.innerText||'').trim().slice(0,200)}))"
            )
            if not isinstance(hrefs, list):
                hrefs = []
            return {"links": hrefs[:max_links], "count": len(hrefs)}
        except Exception as e:
            return {"error": str(e)[:300]}


async def click(arguments: dict[str, Any]) -> dict[str, Any]:
    selector = str(arguments.get("selector") or "").strip()
    timeout_ms = int(arguments.get("timeout_ms") or BROWSER_TIMEOUT_MS)
    if not selector:
        return {"error": "selector is required"}
    async with _lock:
        try:
            page = await _ensure_session()
            await page.click(selector, timeout=timeout_ms)
            return {"clicked": selector, "url_after": page.url}
        except Exception as e:
            return {"error": str(e)[:300]}


async def fill(arguments: dict[str, Any]) -> dict[str, Any]:
    selector = str(arguments.get("selector") or "").strip()
    value = arguments.get("value")
    timeout_ms = int(arguments.get("timeout_ms") or BROWSER_TIMEOUT_MS)
    if not selector or value is None:
        return {"error": "selector and value are required"}
    async with _lock:
        try:
            page = await _ensure_session()
            await page.fill(selector, str(value), timeout=timeout_ms)
            return {"filled": selector}
        except Exception as e:
            return {"error": str(e)[:300]}


async def wait_for(arguments: dict[str, Any]) -> dict[str, Any]:
    selector = str(arguments.get("selector") or "").strip()
    timeout_ms = int(arguments.get("timeout_ms") or BROWSER_TIMEOUT_MS)
    if not selector:
        return {"error": "selector is required"}
    async with _lock:
        try:
            page = await _ensure_session()
            await page.wait_for_selector(selector, timeout=timeout_ms)
            return {"found": True}
        except Exception as e:
            return {"error": str(e)[:300]}


async def close(arguments: dict[str, Any]) -> dict[str, Any]:
    async with _lock:
        await _close_session()
    return {"closed": True}


TOOLS = {
    "navigate": navigate,
    "screenshot": screenshot,
    "extract_text": extract_text,
    "extract_links": extract_links,
    "click": click,
    "fill": fill,
    "wait_for": wait_for,
    "close": close,
}


app = make_app(server_name="browser-use", tools=TOOLS)


if __name__ == "__main__":
    import uvicorn

    # ⚠️ V1 部署约束:**单副本(concurrency=1)** — 进程级单 session,
    # 多 worker 抢同一 page 会冲突。S2 改 per-task session 后才能横向扩。
    port = int(os.getenv("PORT", "7008"))
    uvicorn.run(app, host="0.0.0.0", port=port, workers=1)
