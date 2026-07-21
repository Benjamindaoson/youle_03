"""Smoke tests for the hermes-agent-derived utilities under app.utils.

Coverage targets the *adapted* surface, not full upstream parity — we
just want to catch import regressions and obvious behaviour breakage as
the modules evolve.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.utils.ansi_strip import strip_ansi
from app.utils.binary_extensions import has_binary_extension
from app.utils.context_compressor import (
    CompressorConfig,
    compress_messages,
    estimate_messages_tokens,
    should_compress,
)
from app.utils.error_classifier import FailoverReason, classify_api_error
from app.utils.fuzzy_match import find_closest_lines, fuzzy_find_and_replace
from app.utils.patch_parser import OperationType, parse_v4a_patch
from app.utils.path_security import has_traversal_component, validate_within_dir
from app.utils.prompt_caching import apply_anthropic_cache_control
from app.utils.rate_limit_tracker import parse_rate_limit_headers
from app.utils.redact import mask_secret, redact_sensitive_text
from app.utils.retry_utils import jittered_backoff
from app.utils.schema_sanitizer import (
    sanitize_tool_schemas,
    strip_nullable_unions,
)
from app.utils.tool_output_limits import get_tool_output_limits
from app.utils.tool_result_storage import (
    DEFAULT_BUDGET,
    PERSISTED_OUTPUT_TAG,
    maybe_persist_tool_result,
)
from app.utils.url_safety import is_always_blocked_url, is_safe_url
from app.utils.usage_pricing import (
    CanonicalUsage,
    estimate_usage_cost,
    lookup_pricing,
    normalize_usage,
)

# ── ansi_strip ──────────────────────────────────────────────────────────


def test_strip_ansi_passthrough_clean_text() -> None:
    assert strip_ansi("hello world") == "hello world"


def test_strip_ansi_removes_csi() -> None:
    coloured = "\x1b[31merror\x1b[0m"
    assert strip_ansi(coloured) == "error"


# ── binary_extensions ───────────────────────────────────────────────────


def test_binary_extension_known() -> None:
    assert has_binary_extension("foo.png")
    assert has_binary_extension("path/to/Bar.MP4")
    assert not has_binary_extension("foo.txt")
    assert not has_binary_extension("noext")


# ── path_security ───────────────────────────────────────────────────────


def test_traversal_detection() -> None:
    assert has_traversal_component("../etc/passwd")
    assert not has_traversal_component("subdir/file.txt")


def test_validate_within_dir(tmp_path: Path) -> None:
    inside = tmp_path / "ok.txt"
    inside.write_text("x")
    assert validate_within_dir(inside, tmp_path) is None
    outside = tmp_path.parent
    err = validate_within_dir(outside, tmp_path)
    assert err is not None and "escapes" in err


# ── redact ─────────────────────────────────────────────────────────────


def test_mask_secret_basic() -> None:
    assert mask_secret("sk-proj-abcdef1234567890") == "sk-p...7890"
    assert mask_secret("short") == "***"
    assert mask_secret("") == ""
    assert mask_secret("", empty="(not set)") == "(not set)"


def test_redact_sensitive_text_anthropic_key() -> None:
    text = "Authorization: Bearer sk-ant-api03-AAAAAAAAAAAA1234567890abcdef"
    out = redact_sensitive_text(text, force=True)
    assert "sk-ant" not in out or "..." in out


def test_redact_sensitive_text_jwt() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.signature_here"
    out = redact_sensitive_text(f"token: {jwt}", force=True)
    assert "..." in out


# ── url_safety ─────────────────────────────────────────────────────────


def test_is_always_blocked_metadata() -> None:
    assert is_always_blocked_url("http://169.254.169.254/latest/meta-data/")
    assert is_always_blocked_url("http://metadata.google.internal/")
    assert not is_always_blocked_url("https://example.com/")


def test_is_safe_url_blocks_localhost() -> None:
    # Loopback should be blocked by default.
    assert is_safe_url("http://127.0.0.1/") is False


# ── schema_sanitizer ────────────────────────────────────────────────────


def test_sanitize_collapses_nullable_union() -> None:
    tools = [{
        "type": "function",
        "function": {
            "name": "do_thing",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                    },
                },
            },
        },
    }]
    out = sanitize_tool_schemas(tools)
    name_schema = out[0]["function"]["parameters"]["properties"]["name"]
    assert name_schema.get("type") == "string"
    assert name_schema.get("nullable") is True


def test_strip_nullable_unions_keeps_metadata() -> None:
    schema = {
        "anyOf": [{"type": "integer"}, {"type": "null"}],
        "title": "Count",
        "default": 0,
    }
    out = strip_nullable_unions(schema)
    assert out["type"] == "integer"
    assert out["title"] == "Count"
    assert out["default"] == 0


# ── fuzzy_match ────────────────────────────────────────────────────────


def test_fuzzy_exact_match() -> None:
    new, count, strategy, err = fuzzy_find_and_replace(
        "abc def ghi", "def", "DEF",
    )
    assert err is None
    assert count == 1
    assert strategy == "exact"
    assert new == "abc DEF ghi"


def test_fuzzy_line_trimmed_match() -> None:
    src = "    return foo()\n"
    new, count, strategy, err = fuzzy_find_and_replace(
        src, "return foo()", "return bar()",
    )
    assert err is None
    assert count == 1


def test_fuzzy_did_you_mean() -> None:
    out = find_closest_lines("def hello(", "def hello_world():\n    pass\n")
    assert "hello_world" in out


# ── patch_parser ───────────────────────────────────────────────────────


def test_parse_v4a_simple_update() -> None:
    patch = (
        "*** Begin Patch\n"
        "*** Update File: foo.py\n"
        "@@ context @@\n"
        " context line\n"
        "-old\n"
        "+new\n"
        "*** End Patch\n"
    )
    ops, err = parse_v4a_patch(patch)
    assert err is None
    assert len(ops) == 1
    assert ops[0].operation == OperationType.UPDATE
    assert ops[0].file_path == "foo.py"
    assert ops[0].hunks
    prefixes = [line.prefix for line in ops[0].hunks[0].lines]
    assert "+" in prefixes and "-" in prefixes and " " in prefixes


# ── retry_utils ────────────────────────────────────────────────────────


def test_jittered_backoff_bounds() -> None:
    delay = jittered_backoff(1, base_delay=2.0, max_delay=10.0, jitter_ratio=0.5)
    assert 2.0 <= delay <= 3.5  # 2.0 base + up to 50% jitter
    delay2 = jittered_backoff(5, base_delay=2.0, max_delay=10.0, jitter_ratio=0.5)
    assert delay2 <= 15.0  # capped + jitter


# ── tool_output_limits ─────────────────────────────────────────────────


def test_tool_output_limits_defaults() -> None:
    limits = get_tool_output_limits()
    assert limits["max_bytes"] >= 1
    assert limits["max_lines"] >= 1
    assert limits["max_line_length"] >= 1


# ── prompt_caching ─────────────────────────────────────────────────────


def test_apply_anthropic_cache_control_marks_system_and_tail() -> None:
    msgs = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "Now do thing"},
    ]
    out = apply_anthropic_cache_control(msgs)
    # system → list-with-cache_control on text part
    assert isinstance(out[0]["content"], list)
    assert out[0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    # last message tail also marked
    assert isinstance(out[-1]["content"], list)
    assert out[-1]["content"][0]["cache_control"] == {"type": "ephemeral"}


# ── rate_limit_tracker ─────────────────────────────────────────────────


def test_parse_rate_limit_headers_none_when_absent() -> None:
    assert parse_rate_limit_headers({"content-type": "application/json"}) is None


def test_parse_rate_limit_headers_full_set() -> None:
    headers = {
        "x-ratelimit-limit-requests": "60",
        "x-ratelimit-remaining-requests": "42",
        "x-ratelimit-reset-requests": "30",
        "x-ratelimit-limit-tokens": "100000",
        "x-ratelimit-remaining-tokens": "55000",
        "x-ratelimit-reset-tokens": "30",
    }
    state = parse_rate_limit_headers(headers, provider="openrouter")
    assert state is not None
    assert state.requests_min.limit == 60
    assert state.requests_min.remaining == 42
    assert state.tokens_min.limit == 100_000


# ── error_classifier ───────────────────────────────────────────────────


class _FakeHTTPError(Exception):
    def __init__(self, msg: str, status_code: int | None = None) -> None:
        super().__init__(msg)
        self.status_code = status_code


def test_classify_429_rate_limit() -> None:
    classified = classify_api_error(
        _FakeHTTPError("Too many requests", status_code=429),
        provider="openrouter", model="anthropic/claude-sonnet-4-6",
    )
    assert classified.reason == FailoverReason.rate_limit
    assert classified.retryable is True
    assert classified.should_rotate_credential is True


def test_classify_402_billing_vs_transient() -> None:
    classified = classify_api_error(
        _FakeHTTPError("Insufficient credits", status_code=402),
    )
    assert classified.reason == FailoverReason.billing
    transient = classify_api_error(
        _FakeHTTPError("Usage limit, try again in 5 minutes", status_code=402),
    )
    assert transient.reason == FailoverReason.rate_limit


def test_classify_400_context_overflow() -> None:
    classified = classify_api_error(
        _FakeHTTPError(
            "This model's maximum context length is 200000 tokens",
            status_code=400,
        ),
    )
    assert classified.reason == FailoverReason.context_overflow
    assert classified.should_compress is True


def test_classify_unknown_returns_retryable() -> None:
    classified = classify_api_error(_FakeHTTPError("???"))
    assert classified.reason == FailoverReason.unknown
    assert classified.retryable is True


# ── usage_pricing ──────────────────────────────────────────────────────


def test_lookup_pricing_anthropic_dot_normalisation() -> None:
    entry = lookup_pricing("anthropic", "claude-opus-4.7")
    assert entry is not None
    assert entry.input_cost_per_million is not None


def test_estimate_usage_cost_basic() -> None:
    usage = CanonicalUsage(input_tokens=1_000_000, output_tokens=500_000)
    result = estimate_usage_cost("anthropic", "claude-sonnet-4-6", usage)
    assert result.amount_usd is not None
    # 1M @ $3 in + 0.5M @ $15 out = $3 + $7.50 = $10.50
    assert float(result.amount_usd) == pytest.approx(10.50, rel=1e-3)


def test_normalize_usage_anthropic_shape() -> None:
    class _U:
        input_tokens = 100
        output_tokens = 50
        cache_read_input_tokens = 10
        cache_creation_input_tokens = 5

    usage = normalize_usage(_U(), provider="anthropic")
    assert usage.input_tokens == 100
    assert usage.cache_read_tokens == 10
    assert usage.cache_write_tokens == 5


# ── context_compressor ─────────────────────────────────────────────────


def test_estimate_messages_tokens_nonzero() -> None:
    msgs = [{"role": "user", "content": "hello world " * 100}]
    assert estimate_messages_tokens(msgs) > 100


def test_should_compress_threshold() -> None:
    msgs = [{"role": "user", "content": "x" * 100_000}]
    # ~25K tokens vs context_length=32K → should compress
    assert should_compress(msgs, context_length=32_000) is True
    assert should_compress(msgs, context_length=1_000_000) is False


def test_compress_messages_skips_when_under_threshold() -> None:
    msgs = [{"role": "user", "content": "tiny"}]

    async def summarize(_messages, _budget):  # pragma: no cover
        raise AssertionError("summarize_fn should not be called")

    out = asyncio.run(
        compress_messages(msgs, summarize_fn=summarize, context_length=200_000)
    )
    assert out == msgs


def test_compress_messages_runs_summary_when_large() -> None:
    bulk = "long content " * 5000
    msgs = (
        [{"role": "system", "content": "sys"}]
        + [{"role": "user", "content": bulk}, {"role": "assistant", "content": bulk}] * 5
        + [{"role": "user", "content": "newest"}]
    )

    async def summarize(messages, budget):
        assert messages, "summarizer received empty middle"
        return f"SUMMARY of {len(messages)} msgs ({budget} tok)"

    out = asyncio.run(
        compress_messages(
            msgs,
            summarize_fn=summarize,
            context_length=8_000,
            config=CompressorConfig(head_keep=1, tail_token_budget=2_000),
        )
    )
    assert any(
        "[CONTEXT COMPACTION" in (m.get("content") or "")
        for m in out
        if isinstance(m.get("content"), str)
    )
    assert out[-1]["content"] == "newest"


# ── tool_result_storage ────────────────────────────────────────────────


def test_maybe_persist_tool_result_passthrough_small() -> None:
    async def persist(_key, _body):  # pragma: no cover
        raise AssertionError("should not be called for small content")

    out = asyncio.run(
        maybe_persist_tool_result(
            content="small",
            tool_name="t",
            tool_use_id="x1",
            persist_fn=persist,
        )
    )
    assert out == "small"


def test_maybe_persist_tool_result_spills_large() -> None:
    big = "X" * (DEFAULT_BUDGET.per_tool_threshold + 1000)
    captured: dict = {}

    async def persist(key, body):
        captured["key"] = key
        captured["len"] = len(body)
        return key

    out = asyncio.run(
        maybe_persist_tool_result(
            content=big,
            tool_name="search",
            tool_use_id="abc",
            persist_fn=persist,
        )
    )
    assert PERSISTED_OUTPUT_TAG in out
    assert captured["key"].endswith("abc.txt")
    assert captured["len"] == len(big.encode("utf-8"))
