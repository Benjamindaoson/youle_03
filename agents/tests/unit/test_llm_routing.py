from __future__ import annotations

from agents._common.llm import _task_type_model_chain


def test_no_fallback_hint_keeps_only_explicit_primary_model() -> None:
    assert _task_type_model_chain(
        "long_writing",
        {"primary": "deepseek-v4-pro", "no_fallback": True},
    ) == ["deepseek-v4-pro"]
