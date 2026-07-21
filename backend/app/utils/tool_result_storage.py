"""Spill oversized tool / agent results to OSS instead of context.

Adapted from hermes-agent (MIT) © Nous Research — ``tools/tool_result_storage.py``.
Rewritten around youle_mas's OSS service (instead of upstream's
``env.execute()`` shell heredoc) so the spilled file lives in the same
storage tier as other artefacts and can be re-read via the standard
presigned-URL flow.

Three layers of context-overflow defence:

  1. **Per-tool output cap** — tools pre-truncate before returning.
  2. **Per-result spill** (:func:`maybe_persist_tool_result`) — when a
     single result exceeds its threshold, the full body is uploaded to
     OSS under ``agent-spill/<tool_use_id>.txt`` and the in-context
     payload becomes a ``<persisted-output>`` block with a preview +
     OSS object key.  Agents can fetch the full body via the OSS
     read API.
  3. **Per-turn aggregate budget** (:func:`enforce_turn_budget`) —
     across all tool messages in a turn, if total exceeds the budget,
     the largest non-spilled results are pushed to OSS until under.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

PERSISTED_OUTPUT_TAG = "<persisted-output>"
PERSISTED_OUTPUT_CLOSING_TAG = "</persisted-output>"

DEFAULT_PREVIEW_SIZE_CHARS = 1_500
DEFAULT_PER_TOOL_THRESHOLD = 30_000   # ~7.5K tokens
DEFAULT_TURN_BUDGET = 200_000          # ~50K tokens

#: Type for the OSS-write callback the caller injects.  Returns the OSS
#: object key (or any locator the agent can later resolve).  Keeps this
#: module decoupled from the concrete OSS service for testability.
PersistFn = Callable[[str, bytes], Awaitable[str]]


@dataclass
class BudgetConfig:
    """Per-deployment knobs for the spill behaviour."""

    preview_size: int = DEFAULT_PREVIEW_SIZE_CHARS
    per_tool_threshold: int = DEFAULT_PER_TOOL_THRESHOLD
    turn_budget: int = DEFAULT_TURN_BUDGET
    object_prefix: str = "agent-spill"

    def resolve_threshold(self, tool_name: str | None = None) -> int:
        # Hook for tool-specific overrides; default is the global cap.
        return self.per_tool_threshold


DEFAULT_BUDGET = BudgetConfig()


def generate_preview(
    content: str,
    max_chars: int = DEFAULT_PREVIEW_SIZE_CHARS,
) -> tuple[str, bool]:
    """Truncate at the last newline within *max_chars*.

    Returns ``(preview, has_more)``.  Cleaner cut than a hard slice — the
    LLM sees a balanced fragment instead of a half-word at the end.
    """
    if len(content) <= max_chars:
        return content, False
    truncated = content[:max_chars]
    last_nl = truncated.rfind("\n")
    if last_nl > max_chars // 2:
        truncated = truncated[:last_nl + 1]
    return truncated, True


def _build_persisted_message(
    preview: str,
    has_more: bool,
    original_size: int,
    object_key: str,
) -> str:
    size_kb = original_size / 1024
    size_str = (
        f"{size_kb / 1024:.1f} MB" if size_kb >= 1024 else f"{size_kb:.1f} KB"
    )
    msg = f"{PERSISTED_OUTPUT_TAG}\n"
    msg += f"This tool result was too large ({original_size:,} characters, {size_str}).\n"
    msg += f"Full output saved to OSS: {object_key}\n"
    msg += "Use the OSS read API to fetch specific sections (offset / limit).\n\n"
    msg += f"Preview (first {len(preview)} chars):\n"
    msg += preview
    if has_more:
        msg += "\n..."
    msg += f"\n{PERSISTED_OUTPUT_CLOSING_TAG}"
    return msg


async def maybe_persist_tool_result(
    *,
    content: str,
    tool_name: str,
    tool_use_id: str,
    persist_fn: PersistFn,
    config: BudgetConfig = DEFAULT_BUDGET,
    threshold: int | None = None,
) -> str:
    """Spill *content* to OSS when it exceeds the threshold; else passthrough.

    Args:
        content: Raw tool result (UTF-8 text).
        tool_name: Logged for telemetry; also used for per-tool threshold
            via :meth:`BudgetConfig.resolve_threshold`.
        tool_use_id: Unique ID for this tool call — used as filename root.
        persist_fn: Async ``(key, body) -> key`` callback that uploads
            ``body`` under ``key`` in OSS and returns a locator string.
        config: :class:`BudgetConfig` controlling preview & threshold.
        threshold: Explicit override (precedence over ``config``).

    Returns:
        Either the original *content* (small enough) or the
        ``<persisted-output>`` replacement block.  On upload failure,
        falls back to inline truncation with a clear note.
    """
    effective = (
        threshold if threshold is not None
        else config.resolve_threshold(tool_name)
    )
    if effective == float("inf") or len(content) <= effective:
        return content

    preview, has_more = generate_preview(content, max_chars=config.preview_size)
    object_key = f"{config.object_prefix}/{tool_use_id}.txt"
    try:
        stored_key = await persist_fn(object_key, content.encode("utf-8"))
        logger.info(
            "Persisted oversized tool result: tool=%s id=%s size=%d → %s",
            tool_name, tool_use_id, len(content), stored_key,
        )
        return _build_persisted_message(
            preview, has_more, len(content), stored_key,
        )
    except Exception as exc:
        logger.warning(
            "OSS write failed for tool result %s: %s — falling back to inline truncation",
            tool_use_id, exc,
        )
        return (
            f"{preview}\n\n"
            f"[Truncated: tool response was {len(content):,} chars. "
            f"Full output could not be persisted.]"
        )


async def enforce_turn_budget(
    tool_messages: list[dict],
    *,
    persist_fn: PersistFn,
    config: BudgetConfig = DEFAULT_BUDGET,
) -> list[dict]:
    """Spill the largest non-persisted tool messages until under budget.

    Mutates *tool_messages* in place and returns it.  Already-spilled
    entries (those containing :data:`PERSISTED_OUTPUT_TAG`) are skipped.
    """
    candidates: list[tuple[int, int]] = []
    total_size = 0
    for i, msg in enumerate(tool_messages):
        content = msg.get("content", "")
        size = len(content)
        total_size += size
        if PERSISTED_OUTPUT_TAG not in content:
            candidates.append((i, size))

    if total_size <= config.turn_budget:
        return tool_messages

    candidates.sort(key=lambda x: x[1], reverse=True)
    for idx, size in candidates:
        if total_size <= config.turn_budget:
            break
        msg = tool_messages[idx]
        content = msg["content"]
        tool_use_id = msg.get("tool_call_id", f"budget_{idx}")
        replacement = await maybe_persist_tool_result(
            content=content,
            tool_name="__budget_enforcement__",
            tool_use_id=tool_use_id,
            persist_fn=persist_fn,
            config=config,
            threshold=0,  # force spill
        )
        if replacement != content:
            total_size -= size
            total_size += len(replacement)
            tool_messages[idx]["content"] = replacement
            logger.info(
                "Budget enforcement: spilled tool result %s (%d chars)",
                tool_use_id, size,
            )
    return tool_messages
