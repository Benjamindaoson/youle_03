"""mcp-search:web_search(Tavily,无 key 时降级)+ web_fetch(httpx)。"""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from mcp_servers._shared.http_app import make_app

log = structlog.get_logger(__name__)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
TAVILY_URL = "https://api.tavily.com/search"
SOURCE_CONFIG_PATH = Path(__file__).with_name("source_config.json")


def _load_source_config() -> dict[str, Any]:
    try:
        return json.loads(SOURCE_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("search.source_config_load_failed", err=str(exc))
        return {}


SOURCE_CONFIG = _load_source_config()


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _domain_allowed(url: str, include_domains: list[str], exclude_domains: list[str]) -> bool:
    host = _host(url)
    if not host:
        return False
    if any(host == d or host.endswith(f".{d}") for d in exclude_domains):
        return False
    if include_domains:
        return any(host == d or host.endswith(f".{d}") for d in include_domains)
    return True


def _simplify_query(query: str) -> str:
    years = [token for token in ("2026", "2025", "2024") if token in query]
    keywords = [
        token
        for token in ("电信诈骗", "投资理财", "网恋诈骗", "网络洗钱", "传销", "案件", "新闻", "图片")
        if token in query
    ]
    simplified = " ".join([*years, *keywords])
    return simplified or query[:120]


async def web_search(arguments: dict[str, Any]) -> dict[str, Any]:
    query = arguments.get("query", "").strip()
    max_results = int(arguments.get("max_results", 5))
    source_profile = arguments.get("source_profile") or "anti_fraud_video"
    source_config = SOURCE_CONFIG.get(source_profile, {}) if source_profile else {}
    include_domains = list(arguments.get("include_domains") or source_config.get("include_domains") or [])
    exclude_domains = list(arguments.get("exclude_domains") or source_config.get("exclude_domains") or [])

    if not query:
        return {"results": []}

    effective_query = _simplify_query(query) if include_domains and len(query) > 120 else query

    if TAVILY_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                payload: dict[str, Any] = {
                        "api_key": TAVILY_API_KEY,
                        "query": effective_query,
                        "max_results": max(max_results * 3, max_results),
                        "search_depth": "basic",
                        "include_images": True,
                    }
                if include_domains:
                    payload["include_domains"] = include_domains
                if exclude_domains:
                    payload["exclude_domains"] = exclude_domains
                resp = await client.post(TAVILY_URL, json=payload)
                resp.raise_for_status()
                data = resp.json()
                top_images = data.get("images") or []
                results: list[dict[str, Any]] = []
                for i, r in enumerate(data.get("results", [])):
                    url = r.get("url", "")
                    if not _domain_allowed(url, include_domains, exclude_domains):
                        continue
                    results.append(
                        {
                            "title": r.get("title", ""),
                            "url": url,
                            "snippet": r.get("content", "")[:300],
                            "image_url": r.get("image_url") or (top_images[i] if i < len(top_images) else None),
                        }
                    )
                    if len(results) >= max_results:
                        break
                return {
                    "results": results,
                    "query": query,
                    "effective_query": effective_query,
                    "source_profile": source_profile,
                    "include_domains": include_domains,
                }
        except Exception as e:
            log.warning("tavily.failed", err=str(e))
            # fallthrough to mock

    # 无 key 或失败:返回结构化 mock(用于 dev / CI)
    return {
        "results": [
            {
                "title": f"[mock] 关于「{query}」的结果 {i + 1}",
                "url": f"https://example.com/article/{i}",
                "snippet": "...",
                "image_url": None,
            }
            for i in range(max_results)
        ],
        "_mock": True,
    }


async def web_fetch(arguments: dict[str, Any]) -> dict[str, Any]:
    url = arguments.get("url", "")
    render_js = bool(arguments.get("render_js", False))
    if not url:
        return {"error": "missing_url"}
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "youle/1.0"})
            return {
                "url": url,
                "status": resp.status_code,
                "content_type": resp.headers.get("content-type", ""),
                "content": resp.text[:50_000],
                "render_js": render_js,
            }
    except Exception as e:
        return {"url": url, "error": str(e)}


app = make_app(
    server_name="search",
    tools={"web_search": web_search, "web_fetch": web_fetch},
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7001)
