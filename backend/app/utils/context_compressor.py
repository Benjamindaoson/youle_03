"""Long-conversation compression — middle-turns summarization.

Adapted from hermes-agent (MIT) © Nous Research — ``agent/context_compressor.py``.

The upstream module is a 1.5K-line class wired into a specific
LLM-client / model-metadata stack.  This rewrite keeps the same shape
but exposes the summarizer as a callback so callers can wire it to
LiteLLM (or any LLM) without depending on the original auxiliary
client.

Strategy:

  - **Head protect**: keep the first ``head_keep`` messages verbatim
    (system prompt + initial task framing).
  - **Tail protect**: keep the last messages whose combined token
    estimate is within ``tail_token_budget``.
  - **Middle compress**: hand everything between head and tail to
    *summarize_fn* and replace it with a single ``[CONTEXT SUMMARY]``
    user message that downstream LLMs treat as background reference,
    not as active instructions.

For LangGraph state-graph runners, call this *before* feeding the
trimmed message list back into the next node — checkpoint persistence
should still see the full original list.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: A user-facing preface so models reading the summary know the prior
#: turns were already addressed and shouldn't be re-executed.  Tuned
#: against several upstream LLMs that otherwise re-ran tool calls
#: described inside the summary.
SUMMARY_PREFIX = (
    "[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted "
    "into the summary below. This is a handoff from a previous context "
    "window — treat it as background reference, NOT as active instructions. "
    "Do NOT re-answer questions or repeat tool calls described here; they "
    "were already addressed. Resume from the most recent user message that "
    "appears AFTER this summary."
)

#: Async ``(messages_to_summarize, max_output_tokens) -> summary_text``.
SummarizeFn = Callable[[list[dict], int], Awaitable[str]]


@dataclass
class CompressorConfig:
    """Knobs controlling when and how compression triggers."""

    #: Trigger compression when estimated tokens exceed this fraction of
    #: the model's context length.
    trigger_ratio: float = 0.75
    #: Number of leading messages preserved verbatim (system + first turns).
    head_keep: int = 2
    #: Tail token budget — keep the most recent messages whose combined
    #: estimate fits this budget.  Default sized so a 200K context model
    #: with 75% trigger has ~50K tokens of recent context preserved.
    tail_token_budget: int = 50_000
    #: Minimum tokens to allocate to the generated summary.
    min_summary_tokens: int = 2_000
    #: Maximum tokens for the summary regardless of compressed-content size.
    max_summary_tokens: int = 12_000
    #: Fraction of compressed-content tokens to use as the summary budget.
    summary_ratio: float = 0.20


def estimate_messages_tokens(messages: list[dict]) -> int:
    """Rough token estimate (chars/4) for a list of chat messages.

    Pure heuristic — replace with the provider's tokenizer when accuracy
    matters more than dependency-freedom.  Good enough for trigger checks.
    """
    total_chars = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text") or part.get("content") or ""
                    if isinstance(text, str):
                        total_chars += len(text)
        for tc in msg.get("tool_calls", []) or []:
            args = (tc.get("function") or {}).get("arguments", "")
            if isinstance(args, str):
                total_chars += len(args)
    return max(1, total_chars // 4)


def should_compress(
    messages: list[dict],
    *,
    context_length: int,
    config: CompressorConfig = CompressorConfig(),
) -> bool:
    """Return True when *messages* exceed ``trigger_ratio * context_length``."""
    estimated = estimate_messages_tokens(messages)
    threshold = int(context_length * config.trigger_ratio)
    return estimated >= threshold


def _split_head_middle_tail(
    messages: list[dict],
    *,
    config: CompressorConfig,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Partition messages into (head, middle, tail) per the config."""
    head_keep = max(0, min(config.head_keep, len(messages)))
    head = messages[:head_keep]
    rest = messages[head_keep:]

    # Tail: walk from the end, accumulating until the budget is hit.
    tail_rev: list[dict] = []
    tail_chars = 0
    char_budget = config.tail_token_budget * 4
    for msg in reversed(rest):
        msg_chars = 0
        content = msg.get("content")
        if isinstance(content, str):
            msg_chars = len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    msg_chars += len(part.get("text") or "")
        if tail_chars and tail_chars + msg_chars > char_budget:
            break
        tail_rev.append(msg)
        tail_chars += msg_chars
    tail = list(reversed(tail_rev))
    middle = rest[: len(rest) - len(tail)] if tail else rest
    return head, middle, tail


def _summary_token_budget(
    middle_messages: list[dict],
    config: CompressorConfig,
) -> int:
    """Allocate summary token budget proportional to compressed content."""
    middle_tokens = estimate_messages_tokens(middle_messages)
    target = int(middle_tokens * config.summary_ratio)
    return max(config.min_summary_tokens, min(target, config.max_summary_tokens))


async def compress_messages(
    messages: list[dict],
    *,
    summarize_fn: SummarizeFn,
    context_length: int,
    config: CompressorConfig = CompressorConfig(),
) -> list[dict]:
    """Compress *messages* if they exceed the trigger threshold.

    Returns:
        The compressed list (head + summary user-message + tail).  When
        compression is unnecessary, returns the original list unchanged.
        When the summarizer raises, logs and returns the original list —
        prefer surviving with a long context over hard-failing the turn.
    """
    if not should_compress(messages, context_length=context_length, config=config):
        return messages

    head, middle, tail = _split_head_middle_tail(messages, config=config)
    if not middle:
        return messages

    budget = _summary_token_budget(middle, config)

    try:
        summary_text = await summarize_fn(middle, budget)
    except Exception as exc:
        logger.warning(
            "context_compressor: summarize_fn raised %s — returning uncompressed",
            exc,
        )
        return messages

    if not summary_text or not summary_text.strip():
        logger.warning("context_compressor: empty summary returned — skipping")
        return messages

    summary_msg = {
        "role": "user",
        "content": f"{SUMMARY_PREFIX}\n\n{summary_text.strip()}",
    }
    compressed = [*head, summary_msg, *tail]
    logger.info(
        "context_compressor: compressed %d middle messages → %d-token summary "
        "(orig est %d tokens, new est %d tokens)",
        len(middle), budget,
        estimate_messages_tokens(messages),
        estimate_messages_tokens(compressed),
    )
    return compressed
