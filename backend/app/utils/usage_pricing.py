"""LLM usage normalization & cost estimation.

Adapted from hermes-agent (MIT) © Nous Research — ``agent/usage_pricing.py``.

Trimmed to the parts that don't depend on hermes's auxiliary fetchers
(``models.dev``, ``OpenRouter /models``, etc.):

  - ``CanonicalUsage`` token bucket dataclass.
  - ``normalize_usage`` for OpenAI / Anthropic / Codex Responses API.
  - Static ``_OFFICIAL_DOCS_PRICING`` snapshot for major models.
  - ``estimate_usage_cost`` → :class:`CostResult`.

If you need live pricing fetched from the provider, wire your own
fetcher and feed a ``PricingEntry`` into :func:`estimate_with_pricing`.

Pricing snapshot below is current as of 2026-05.  Update when you ship a
new model price tier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

_ZERO = Decimal("0")
_ONE_MILLION = Decimal("1000000")

CostStatus = Literal["actual", "estimated", "included", "unknown"]
CostSource = Literal[
    "provider_cost_api",
    "provider_models_api",
    "official_docs_snapshot",
    "user_override",
    "custom_contract",
    "none",
]


@dataclass(frozen=True)
class CanonicalUsage:
    """Token-bucket counts normalized across provider response shapes."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    request_count: int = 1
    raw_usage: dict[str, Any] | None = None

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.output_tokens


@dataclass(frozen=True)
class PricingEntry:
    input_cost_per_million: Decimal | None = None
    output_cost_per_million: Decimal | None = None
    cache_read_cost_per_million: Decimal | None = None
    cache_write_cost_per_million: Decimal | None = None
    request_cost: Decimal | None = None
    source: CostSource = "none"
    source_url: str | None = None
    pricing_version: str | None = None
    fetched_at: datetime | None = None


@dataclass(frozen=True)
class CostResult:
    amount_usd: Decimal | None
    status: CostStatus
    source: CostSource
    label: str
    fetched_at: datetime | None = None
    pricing_version: str | None = None
    notes: tuple[str, ...] = ()


# ── Pricing snapshot (2026-05) ────────────────────────────────────────

_OFFICIAL_DOCS_PRICING: dict[tuple[str, str], PricingEntry] = {
    # ── Anthropic ─────────────────────────────────────────────────────
    ("anthropic", "claude-opus-4-7"): PricingEntry(
        input_cost_per_million=Decimal("5.00"),
        output_cost_per_million=Decimal("25.00"),
        cache_read_cost_per_million=Decimal("0.50"),
        cache_write_cost_per_million=Decimal("6.25"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-05",
    ),
    ("anthropic", "claude-opus-4-6"): PricingEntry(
        input_cost_per_million=Decimal("5.00"),
        output_cost_per_million=Decimal("25.00"),
        cache_read_cost_per_million=Decimal("0.50"),
        cache_write_cost_per_million=Decimal("6.25"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-05",
    ),
    ("anthropic", "claude-sonnet-4-6"): PricingEntry(
        input_cost_per_million=Decimal("3.00"),
        output_cost_per_million=Decimal("15.00"),
        cache_read_cost_per_million=Decimal("0.30"),
        cache_write_cost_per_million=Decimal("3.75"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-05",
    ),
    ("anthropic", "claude-haiku-4-5"): PricingEntry(
        input_cost_per_million=Decimal("1.00"),
        output_cost_per_million=Decimal("5.00"),
        cache_read_cost_per_million=Decimal("0.10"),
        cache_write_cost_per_million=Decimal("1.25"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-05",
    ),
    ("anthropic", "claude-3-5-sonnet-20241022"): PricingEntry(
        input_cost_per_million=Decimal("3.00"),
        output_cost_per_million=Decimal("15.00"),
        cache_read_cost_per_million=Decimal("0.30"),
        cache_write_cost_per_million=Decimal("3.75"),
        source="official_docs_snapshot",
        pricing_version="anthropic-pricing-2026-05",
    ),
    ("anthropic", "claude-3-5-haiku-20241022"): PricingEntry(
        input_cost_per_million=Decimal("0.80"),
        output_cost_per_million=Decimal("4.00"),
        cache_read_cost_per_million=Decimal("0.08"),
        cache_write_cost_per_million=Decimal("1.00"),
        source="official_docs_snapshot",
        pricing_version="anthropic-pricing-2026-05",
    ),
    # ── OpenAI ────────────────────────────────────────────────────────
    ("openai", "gpt-4o"): PricingEntry(
        input_cost_per_million=Decimal("2.50"),
        output_cost_per_million=Decimal("10.00"),
        cache_read_cost_per_million=Decimal("1.25"),
        source="official_docs_snapshot",
        source_url="https://openai.com/api/pricing/",
        pricing_version="openai-pricing-2026-03-16",
    ),
    ("openai", "gpt-4o-mini"): PricingEntry(
        input_cost_per_million=Decimal("0.15"),
        output_cost_per_million=Decimal("0.60"),
        cache_read_cost_per_million=Decimal("0.075"),
        source="official_docs_snapshot",
        pricing_version="openai-pricing-2026-03-16",
    ),
    ("openai", "gpt-4.1"): PricingEntry(
        input_cost_per_million=Decimal("2.00"),
        output_cost_per_million=Decimal("8.00"),
        cache_read_cost_per_million=Decimal("0.50"),
        source="official_docs_snapshot",
        pricing_version="openai-pricing-2026-03-16",
    ),
    ("openai", "gpt-4.1-mini"): PricingEntry(
        input_cost_per_million=Decimal("0.40"),
        output_cost_per_million=Decimal("1.60"),
        cache_read_cost_per_million=Decimal("0.10"),
        source="official_docs_snapshot",
        pricing_version="openai-pricing-2026-03-16",
    ),
    ("openai", "o3"): PricingEntry(
        input_cost_per_million=Decimal("10.00"),
        output_cost_per_million=Decimal("40.00"),
        cache_read_cost_per_million=Decimal("2.50"),
        source="official_docs_snapshot",
        pricing_version="openai-pricing-2026-03-16",
    ),
    ("openai", "o3-mini"): PricingEntry(
        input_cost_per_million=Decimal("1.10"),
        output_cost_per_million=Decimal("4.40"),
        cache_read_cost_per_million=Decimal("0.55"),
        source="official_docs_snapshot",
        pricing_version="openai-pricing-2026-03-16",
    ),
    # ── DeepSeek ──────────────────────────────────────────────────────
    ("deepseek", "deepseek-chat"): PricingEntry(
        input_cost_per_million=Decimal("0.14"),
        output_cost_per_million=Decimal("0.28"),
        source="official_docs_snapshot",
        pricing_version="deepseek-pricing-2026-03-16",
    ),
    ("deepseek", "deepseek-reasoner"): PricingEntry(
        input_cost_per_million=Decimal("0.55"),
        output_cost_per_million=Decimal("2.19"),
        source="official_docs_snapshot",
        pricing_version="deepseek-pricing-2026-03-16",
    ),
    # ── Google Gemini ─────────────────────────────────────────────────
    ("google", "gemini-2.5-pro"): PricingEntry(
        input_cost_per_million=Decimal("1.25"),
        output_cost_per_million=Decimal("10.00"),
        source="official_docs_snapshot",
        pricing_version="google-pricing-2026-03-16",
    ),
    ("google", "gemini-2.5-flash"): PricingEntry(
        input_cost_per_million=Decimal("0.15"),
        output_cost_per_million=Decimal("0.60"),
        source="official_docs_snapshot",
        pricing_version="google-pricing-2026-03-16",
    ),
    ("google", "gemini-2.0-flash"): PricingEntry(
        input_cost_per_million=Decimal("0.10"),
        output_cost_per_million=Decimal("0.40"),
        source="official_docs_snapshot",
        pricing_version="google-pricing-2026-03-16",
    ),
    # ── Alibaba Tongyi (Qwen) ─────────────────────────────────────────
    ("dashscope", "qwen-max"): PricingEntry(
        input_cost_per_million=Decimal("0.42"),  # CNY 2.40 / 1M ≈ USD
        output_cost_per_million=Decimal("1.70"),  # CNY 9.60 / 1M ≈ USD
        source="official_docs_snapshot",
        pricing_version="dashscope-pricing-2026-04",
    ),
    ("dashscope", "qwen-plus"): PricingEntry(
        input_cost_per_million=Decimal("0.11"),
        output_cost_per_million=Decimal("0.28"),
        source="official_docs_snapshot",
        pricing_version="dashscope-pricing-2026-04",
    ),
    # ── MiniMax ───────────────────────────────────────────────────────
    ("minimax", "minimax-m2.7"): PricingEntry(
        input_cost_per_million=Decimal("0.30"),
        output_cost_per_million=Decimal("1.20"),
        source="official_docs_snapshot",
        pricing_version="minimax-pricing-2026-04",
    ),
}


# ── Helpers ──────────────────────────────────────────────────────────


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _normalize_anthropic_model_name(model: str) -> str:
    """Normalize Anthropic model variants to canonical form.

    Handles: dot notation (``4.7`` → ``4-7``), provider prefix stripping.
    """
    name = model.lower().strip()
    if name.startswith("anthropic/"):
        name = name[len("anthropic/"):]
    name = re.sub(r"(\d+)\.(\d+)", r"\1-\2", name)
    return name


def lookup_pricing(provider: str, model: str) -> PricingEntry | None:
    """Look up a static pricing entry for ``(provider, model)``.

    Returns None when the pair isn't in the snapshot — caller may fall
    back to a live fetcher.
    """
    p = (provider or "").strip().lower()
    m = (model or "").strip().lower()
    entry = _OFFICIAL_DOCS_PRICING.get((p, m))
    if entry:
        return entry
    if p == "anthropic":
        normalized = _normalize_anthropic_model_name(m)
        if normalized != m:
            return _OFFICIAL_DOCS_PRICING.get((p, normalized))
    return None


# ── Usage normalization ──────────────────────────────────────────────


def normalize_usage(
    response_usage: Any,
    *,
    provider: str | None = None,
    api_mode: str | None = None,
) -> CanonicalUsage:
    """Normalize raw response usage into canonical token buckets.

    Handles three API shapes:
      - **Anthropic Messages**:
        ``input_tokens`` / ``output_tokens`` / ``cache_read_input_tokens`` /
        ``cache_creation_input_tokens``.
      - **Codex Responses**:
        ``input_tokens`` includes cache; ``input_tokens_details.cached_tokens``
        breaks it out.
      - **OpenAI Chat Completions** (default):
        ``prompt_tokens`` / ``completion_tokens`` /
        ``prompt_tokens_details.cached_tokens``.  Also handles OpenRouter's
        Anthropic top-level cache fields when proxying Claude.

    *api_mode* one of ``"anthropic_messages"``, ``"codex_responses"``, or
    omit for OpenAI default.
    """
    if not response_usage:
        return CanonicalUsage()

    provider_name = (provider or "").strip().lower()
    mode = (api_mode or "").strip().lower()

    if mode == "anthropic_messages" or provider_name == "anthropic":
        input_tokens = _to_int(getattr(response_usage, "input_tokens", 0))
        output_tokens = _to_int(getattr(response_usage, "output_tokens", 0))
        cache_read_tokens = _to_int(
            getattr(response_usage, "cache_read_input_tokens", 0)
        )
        cache_write_tokens = _to_int(
            getattr(response_usage, "cache_creation_input_tokens", 0)
        )
    elif mode == "codex_responses":
        input_total = _to_int(getattr(response_usage, "input_tokens", 0))
        output_tokens = _to_int(getattr(response_usage, "output_tokens", 0))
        details = getattr(response_usage, "input_tokens_details", None)
        cache_read_tokens = _to_int(
            getattr(details, "cached_tokens", 0) if details else 0
        )
        cache_write_tokens = _to_int(
            getattr(details, "cache_creation_tokens", 0) if details else 0
        )
        input_tokens = max(
            0, input_total - cache_read_tokens - cache_write_tokens
        )
    else:
        prompt_total = _to_int(getattr(response_usage, "prompt_tokens", 0))
        output_tokens = _to_int(getattr(response_usage, "completion_tokens", 0))
        details = getattr(response_usage, "prompt_tokens_details", None)
        cache_read_tokens = _to_int(
            getattr(details, "cached_tokens", 0) if details else 0
        )
        if not cache_read_tokens:
            cache_read_tokens = _to_int(
                getattr(response_usage, "cache_read_input_tokens", 0)
            )
        cache_write_tokens = _to_int(
            getattr(details, "cache_write_tokens", 0) if details else 0
        )
        if not cache_write_tokens:
            cache_write_tokens = _to_int(
                getattr(response_usage, "cache_creation_input_tokens", 0)
            )
        input_tokens = max(
            0, prompt_total - cache_read_tokens - cache_write_tokens
        )

    reasoning_tokens = 0
    output_details = getattr(response_usage, "output_tokens_details", None)
    if output_details:
        reasoning_tokens = _to_int(
            getattr(output_details, "reasoning_tokens", 0)
        )

    return CanonicalUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        reasoning_tokens=reasoning_tokens,
    )


# ── Cost estimation ───────────────────────────────────────────────────


def estimate_with_pricing(
    usage: CanonicalUsage,
    entry: PricingEntry,
) -> CostResult:
    """Compute :class:`CostResult` from *usage* and a *PricingEntry*.

    Use this when you fetched pricing from a live source and want the
    same arithmetic as :func:`estimate_usage_cost`.
    """
    notes: list[str] = []
    amount = _ZERO

    if usage.input_tokens and entry.input_cost_per_million is None:
        return CostResult(None, "unknown", entry.source, "n/a")
    if usage.output_tokens and entry.output_cost_per_million is None:
        return CostResult(None, "unknown", entry.source, "n/a")
    if usage.cache_read_tokens and entry.cache_read_cost_per_million is None:
        return CostResult(
            None, "unknown", entry.source, "n/a",
            notes=("cache-read pricing unavailable",),
        )
    if usage.cache_write_tokens and entry.cache_write_cost_per_million is None:
        return CostResult(
            None, "unknown", entry.source, "n/a",
            notes=("cache-write pricing unavailable",),
        )

    if entry.input_cost_per_million is not None:
        amount += (
            Decimal(usage.input_tokens) * entry.input_cost_per_million
            / _ONE_MILLION
        )
    if entry.output_cost_per_million is not None:
        amount += (
            Decimal(usage.output_tokens) * entry.output_cost_per_million
            / _ONE_MILLION
        )
    if entry.cache_read_cost_per_million is not None:
        amount += (
            Decimal(usage.cache_read_tokens) * entry.cache_read_cost_per_million
            / _ONE_MILLION
        )
    if entry.cache_write_cost_per_million is not None:
        amount += (
            Decimal(usage.cache_write_tokens) * entry.cache_write_cost_per_million
            / _ONE_MILLION
        )
    if entry.request_cost is not None and usage.request_count:
        amount += Decimal(usage.request_count) * entry.request_cost

    status: CostStatus = "estimated"
    label = f"~${amount:.4f}"
    if entry.source == "none" and amount == _ZERO:
        status = "included"
        label = "included"

    return CostResult(
        amount_usd=amount,
        status=status,
        source=entry.source,
        label=label,
        fetched_at=entry.fetched_at,
        pricing_version=entry.pricing_version,
        notes=tuple(notes),
    )


def estimate_usage_cost(
    provider: str,
    model: str,
    usage: CanonicalUsage,
) -> CostResult:
    """Estimate cost from the static pricing snapshot.

    Returns ``CostResult(amount_usd=None, status="unknown")`` when the
    ``(provider, model)`` is not in the snapshot.
    """
    entry = lookup_pricing(provider, model)
    if not entry:
        return CostResult(None, "unknown", "none", "n/a")
    return estimate_with_pricing(usage, entry)


# ── Display helpers ───────────────────────────────────────────────────


def format_token_count_compact(value: int) -> str:
    """Compact token count for status bars: 1234567 → '1.23M', 7989 → '7.99K'."""
    abs_value = abs(int(value))
    if abs_value < 1_000:
        return str(int(value))

    sign = "-" if value < 0 else ""
    units = ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K"))
    for threshold, suffix in units:
        if abs_value >= threshold:
            scaled = abs_value / threshold
            if scaled < 10:
                text = f"{scaled:.2f}"
            elif scaled < 100:
                text = f"{scaled:.1f}"
            else:
                text = f"{scaled:.0f}"
            if "." in text:
                text = text.rstrip("0").rstrip(".")
            return f"{sign}{text}{suffix}"
    return f"{value:,}"
