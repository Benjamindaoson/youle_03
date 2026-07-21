"""Anthropic prompt caching helper (system + last-3 strategy).

Adapted from hermes-agent (MIT) © Nous Research — ``agent/prompt_caching.py``.

Reduces input-token costs by ~75% on multi-turn conversations.  Anthropic
allows up to 4 ``cache_control`` breakpoints per request — this helper
places them at:

    1. The system prompt (stable across turns).
    2-4. The last 3 non-system messages (rolling window).

Pure function; safe to call before handing messages off to the Anthropic
SDK or to a LiteLLM call routed at an Anthropic-family model.

Usage::

    from app.utils.prompt_caching import apply_anthropic_cache_control
    cached = apply_anthropic_cache_control(messages)
    response = client.messages.create(model="claude-...", messages=cached, ...)
"""

from __future__ import annotations

import copy
from typing import Any


def _apply_cache_marker(
    msg: dict,
    cache_marker: dict,
    native_anthropic: bool = False,
) -> None:
    """Add ``cache_control`` to a single message, handling all content shapes."""
    role = msg.get("role", "")
    content = msg.get("content")

    if role == "tool":
        if native_anthropic:
            msg["cache_control"] = cache_marker
        return

    if content is None or content == "":
        msg["cache_control"] = cache_marker
        return

    if isinstance(content, str):
        msg["content"] = [
            {"type": "text", "text": content, "cache_control": cache_marker}
        ]
        return

    if isinstance(content, list) and content:
        last = content[-1]
        if isinstance(last, dict):
            last["cache_control"] = cache_marker


def apply_anthropic_cache_control(
    api_messages: list[dict[str, Any]],
    cache_ttl: str = "5m",
    native_anthropic: bool = False,
) -> list[dict[str, Any]]:
    """Apply ``system_and_3`` caching to *api_messages* for Anthropic models.

    Args:
        api_messages: Chat-completions style ``[{role, content, ...}]``.
        cache_ttl: ``"5m"`` (default, free) or ``"1h"`` (paid extension).
        native_anthropic: True when sending directly via the Anthropic SDK
            rather than an OpenAI-compatible proxy.  Affects how
            ``cache_control`` is placed on ``role: "tool"`` messages.

    Returns:
        Deep copy of *api_messages* with up to 4 ``cache_control`` markers.
    """
    messages = copy.deepcopy(api_messages)
    if not messages:
        return messages

    marker: dict[str, Any] = {"type": "ephemeral"}
    if cache_ttl == "1h":
        marker["ttl"] = "1h"

    breakpoints_used = 0
    if messages[0].get("role") == "system":
        _apply_cache_marker(messages[0], marker, native_anthropic=native_anthropic)
        breakpoints_used += 1

    remaining = 4 - breakpoints_used
    non_sys = [i for i in range(len(messages)) if messages[i].get("role") != "system"]
    for idx in non_sys[-remaining:]:
        _apply_cache_marker(messages[idx], marker, native_anthropic=native_anthropic)

    return messages
