"""httpx event-hook helpers backed by ``app.utils.url_safety``.

Drop-in for any ``httpx.AsyncClient`` / ``httpx.Client`` that fetches from
URLs not under our control (web scraping skills, image downloads, MCP
sidecar replies that include external links, …).

Usage::

    from app.utils.httpx_safe import safe_async_client_kwargs
    client = httpx.AsyncClient(**safe_async_client_kwargs(allow_internal=False))

For internal services (LiteLLM proxy, MCP sidecars on the docker network)
pass ``allow_internal=True`` so the loopback / 10.0.0.0/8 / docker bridge
resolutions don't get blocked.

Two layers:
  - **request hook** — runs *before* DNS/connect, blocks based on
    :func:`app.utils.url_safety.is_always_blocked_url`.
  - **redirect hook** — re-validates the ``Location`` target after each
    3xx so an upstream can't bounce us into a private IP.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import httpx

from app.utils.url_safety import is_always_blocked_url, is_safe_url

logger = logging.getLogger(__name__)


class BlockedURLError(httpx.RequestError):
    """Raised when a request target fails the SSRF safety check.

    Subclasses ``httpx.RequestError`` (not bare ``HTTPError``) because only
    ``RequestError`` accepts a ``request=`` kwarg in its constructor.
    Catchers that already handle ``RequestError`` for connection failures
    will naturally pick up SSRF blocks too — that's the right behaviour:
    a blocked URL is a connection-failure mode from the caller's POV.
    """


def _check_request(allow_internal: bool):
    async def _hook(request: httpx.Request) -> None:
        url = str(request.url)
        if is_always_blocked_url(url):
            logger.warning("httpx_safe always-blocked target: %s", url)
            raise BlockedURLError(
                f"URL targets always-blocked endpoint (cloud metadata): {url}",
                request=request,
            )
        if not allow_internal and not is_safe_url(url):
            logger.warning("httpx_safe private-blocked target: %s", url)
            raise BlockedURLError(
                f"URL targets private/internal address: {url}",
                request=request,
            )
    return _hook


def _check_response(allow_internal: bool):
    async def _hook(response: httpx.Response) -> None:
        # Only inspect 3xx — terminal responses don't need a redirect check.
        if response.status_code < 300 or response.status_code >= 400:
            return
        location = response.headers.get("location")
        if not location:
            return
        # httpx resolves the redirect target as response.next_request, but
        # that's only set when ``follow_redirects=True``.  Build it manually
        # to validate even when the caller follows redirects themselves.
        try:
            next_url = response.url.join(location)
        except Exception:
            return
        target = str(next_url)
        if is_always_blocked_url(target):
            logger.warning("httpx_safe redirect → always-blocked: %s", target)
            raise BlockedURLError(
                f"Redirect target is always-blocked: {target}",
                request=response.request,
            )
        if not allow_internal and not is_safe_url(target):
            logger.warning("httpx_safe redirect → private-blocked: %s", target)
            raise BlockedURLError(
                f"Redirect target is private/internal: {target}",
                request=response.request,
            )
    return _hook


def safe_event_hooks(allow_internal: bool = False) -> Mapping[str, list]:
    """Build httpx ``event_hooks`` dict that enforces SSRF safety.

    Args:
        allow_internal: When True, only the always-blocked floor (cloud
            metadata IPs, ``metadata.google.internal``) is enforced —
            loopback / private nets are allowed.  Use for clients that
            target known internal services (LiteLLM proxy, MCP sidecars).
    """
    return {
        "request": [_check_request(allow_internal)],
        "response": [_check_response(allow_internal)],
    }


def safe_async_client_kwargs(
    allow_internal: bool = False,
    **extra: Any,
) -> dict:
    """Return kwargs to splat into ``httpx.AsyncClient(**kwargs)``.

    Caller-supplied ``event_hooks`` are merged with the safety hooks; the
    safety hooks always run first, so a downstream hook seeing the request
    knows it's already been validated.
    """
    base_hooks = safe_event_hooks(allow_internal=allow_internal)
    user_hooks = extra.pop("event_hooks", None) or {}
    merged_hooks: dict[str, list] = {
        "request": list(base_hooks["request"]),
        "response": list(base_hooks["response"]),
    }
    for key, vals in user_hooks.items():
        merged_hooks.setdefault(key, []).extend(vals or [])
    return {"event_hooks": merged_hooks, **extra}
