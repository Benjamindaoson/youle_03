"""Smoke tests for the streaming think-tag scrubber.

The scrubber's job is to suppress reasoning blocks across delta
boundaries — these tests cover the boundary cases the upstream wiki
documents as historically buggy.
"""

from __future__ import annotations

from agents._common.think_scrubber import StreamingThinkScrubber


def _drive(s: StreamingThinkScrubber, parts: list[str]) -> str:
    out = []
    for p in parts:
        out.append(s.feed(p))
    out.append(s.flush())
    return "".join(out)


def test_passthrough_clean_text() -> None:
    s = StreamingThinkScrubber()
    assert _drive(s, ["hello ", "world"]) == "hello world"


def test_closed_pair_suppressed() -> None:
    s = StreamingThinkScrubber()
    out = _drive(s, ["before <think>secret</think> after"])
    assert "secret" not in out
    assert "before" in out and "after" in out


def test_split_open_tag_across_deltas() -> None:
    s = StreamingThinkScrubber()
    out = _drive(s, ["<thi", "nk>", "secret\n", "still secret", "</think>visible"])
    assert "secret" not in out
    assert "visible" in out


def test_open_tag_at_block_boundary_only() -> None:
    s = StreamingThinkScrubber()
    # tag mid-sentence, no boundary → not suppressed (kept as text)
    out = _drive(s, ['use <think> tags wisely'])
    assert "<think>" in out


def test_unterminated_block_at_flush_drops_content() -> None:
    s = StreamingThinkScrubber()
    out = _drive(s, ["<think>partial reasoning that never closes"])
    # Per scrubber contract: unterminated reasoning at flush is dropped.
    assert "partial reasoning" not in out


def test_reset_between_turns() -> None:
    s = StreamingThinkScrubber()
    _drive(s, ["<think>turn 1 reasoning"])
    s.reset()
    out = _drive(s, ["clean turn 2 output"])
    assert out == "clean turn 2 output"
