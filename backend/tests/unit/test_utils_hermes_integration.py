"""Integration smoke tests for hermes-utility wirings.

Validates that:
  - logging.RedactingFormatter actually scrubs an API key in stdlib logging
  - structlog `_redact_full_event` processor scrubs Bearer tokens
  - httpx_safe event hooks block cloud-metadata URLs
  - schema_sanitizer kicks in on react_runner-shaped tool list
  - prompt_caching is applied for Anthropic-family models
  - error_classifier maps real httpx errors

These are *integration* tests — not exercising every corner of each util
(those live in test_utils_hermes_port.py) but proving the wires are real.
"""

from __future__ import annotations

import asyncio
import logging
import os

import httpx
import pytest

from app.utils.error_classifier import FailoverReason, classify_api_error
from app.utils.httpx_safe import (
    BlockedURLError,
    safe_async_client_kwargs,
    safe_event_hooks,
)
from app.utils.prompt_caching import apply_anthropic_cache_control
from app.utils.redact import RedactingFormatter
from app.utils.schema_sanitizer import sanitize_tool_schemas

# ── RedactingFormatter (stdlib logging) ─────────────────────────────


def test_redacting_formatter_scrubs_anthropic_key(caplog) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter("%(message)s"))

    test_logger = logging.getLogger("redact_smoke_logger")
    test_logger.handlers.clear()
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.INFO)

    # Force redaction on (test isolation against env-overridden disable)
    os.environ["YOULE_REDACT_SECRETS"] = "true"

    raw = "Authorization: Bearer sk-ant-api03-AAAAAAAAAAAA1234567890abcdefXYZ"
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname="", lineno=0,
        msg=raw, args=(), exc_info=None,
    )
    rendered = handler.formatter.format(record)
    assert "sk-ant" not in rendered or "..." in rendered
    # Strict guarantee: the body of the secret is gone
    assert "1234567890abcdefXYZ" not in rendered


def test_redacting_formatter_passthrough_clean_text() -> None:
    fmt = RedactingFormatter("%(message)s")
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname="", lineno=0,
        msg="user 123 logged in", args=(), exc_info=None,
    )
    assert fmt.format(record) == "user 123 logged in"


# ── structlog wiring ────────────────────────────────────────────────


def test_structlog_redact_processor_runs() -> None:
    """`_redact_full_event` is wired into the processor chain."""
    from app import logging as app_logging

    # Recreate the processor and run it directly
    event = {"event": "request", "auth_header": "Bearer sk-proj-abcdefABCDEF1234567890XYZ"}
    out = app_logging._redact_full_event(None, "info", dict(event))  # type: ignore[arg-type]
    val = out["auth_header"]
    assert "1234567890XYZ" not in val
    # The token's body should be masked
    assert "..." in val or "***" in val or "REDACTED" in val.upper()


# ── httpx_safe ──────────────────────────────────────────────────────


def test_safe_event_hooks_blocks_cloud_metadata() -> None:
    hooks = safe_event_hooks(allow_internal=False)
    request_hook = hooks["request"][0]

    request = httpx.Request("GET", "http://169.254.169.254/latest/meta-data/")
    with pytest.raises(BlockedURLError):
        asyncio.run(request_hook(request))


def test_safe_event_hooks_allow_internal_blocks_metadata_only() -> None:
    """allow_internal=True still blocks cloud metadata, lets loopback pass."""
    hooks = safe_event_hooks(allow_internal=True)
    request_hook = hooks["request"][0]

    # Cloud metadata still blocked
    blocked = httpx.Request("GET", "http://169.254.169.254/")
    with pytest.raises(BlockedURLError):
        asyncio.run(request_hook(blocked))

    # Loopback allowed
    loopback = httpx.Request("GET", "http://127.0.0.1:5000/health")
    asyncio.run(request_hook(loopback))  # no raise


def test_safe_async_client_kwargs_returns_event_hooks() -> None:
    kwargs = safe_async_client_kwargs(allow_internal=True)
    assert "event_hooks" in kwargs
    assert "request" in kwargs["event_hooks"]
    assert "response" in kwargs["event_hooks"]


# ── schema_sanitizer wiring (mimics react_runner._build_tools shape) ─


def test_react_tool_list_passes_through_sanitizer() -> None:
    """A react_runner-shaped tool list survives sanitizer round-trip."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "mcp__search__web_search",
                "description": "MCP 工具 search/web_search",
                "parameters": {"type": "object", "additionalProperties": True},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "agent_finish",
                "description": "Finish",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "markdown": {
                            # nullable union — should be collapsed
                            "anyOf": [{"type": "string"}, {"type": "null"}],
                            "description": "Output text",
                        },
                    },
                    "required": ["markdown"],
                },
            },
        },
    ]
    out = sanitize_tool_schemas(tools)
    # Top-level still object with properties
    assert out[0]["function"]["parameters"]["type"] == "object"
    # Nullable union collapsed
    md_schema = out[1]["function"]["parameters"]["properties"]["markdown"]
    assert md_schema.get("type") == "string"


# ── prompt_caching for Anthropic family ─────────────────────────────


def test_prompt_caching_applied_for_anthropic() -> None:
    msgs = [
        {"role": "system", "content": "Be helpful."},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "Continue"},
    ]
    out = apply_anthropic_cache_control(msgs)
    # System message → list with cache_control on the text part
    assert isinstance(out[0]["content"], list)
    assert out[0]["content"][0]["cache_control"]["type"] == "ephemeral"
    # Latest user also gets cache_control
    assert isinstance(out[-1]["content"], list)
    assert out[-1]["content"][0]["cache_control"]["type"] == "ephemeral"


# ── error_classifier on a real httpx-shaped exception ──────────────


def test_classifier_handles_httpx_status_error() -> None:
    """A 429 from httpx-style error is classified as rate_limit."""
    request = httpx.Request("POST", "https://api.example.com/v1/chat")
    response = httpx.Response(
        status_code=429,
        request=request,
        text='{"error":{"message":"rate limit"}}',
    )
    exc = httpx.HTTPStatusError("429", request=request, response=response)
    classified = classify_api_error(exc, model="claude-sonnet-4-6")
    assert classified.reason == FailoverReason.rate_limit
    assert classified.retryable is True
    assert classified.should_rotate_credential is True


def test_classifier_context_overflow_400() -> None:
    request = httpx.Request("POST", "https://api.example.com/v1/chat")
    response = httpx.Response(
        status_code=400,
        request=request,
        text='{"error":{"message":"This model\'s maximum context length is 200000 tokens, however your prompt resulted in 250000 tokens."}}',
    )
    exc = httpx.HTTPStatusError("400", request=request, response=response)
    classified = classify_api_error(exc, model="gpt-4.1")
    assert classified.reason == FailoverReason.context_overflow
    assert classified.should_compress is True


# ── llm._maybe_cache_anthropic gate ─────────────────────────────────


def test_llm_maybe_cache_anthropic_only_for_claude() -> None:
    from agents._common.llm import _maybe_cache_anthropic

    msgs = [{"role": "user", "content": "hi"}]

    # Non-Anthropic: passthrough
    out_gpt = _maybe_cache_anthropic("gpt-4.1", list(msgs))
    assert out_gpt[0]["content"] == "hi"

    # Anthropic family: cache_control injected
    out_claude = _maybe_cache_anthropic("claude-sonnet-4-6", list(msgs))
    # User message had no system before it, but it should be marked
    # because it's the only / latest non-system message.
    item = out_claude[0]["content"]
    if isinstance(item, list):
        assert any(
            isinstance(x, dict) and x.get("cache_control")
            for x in item
        )
    else:
        # Or the message itself got cache_control
        assert out_claude[0].get("cache_control")
