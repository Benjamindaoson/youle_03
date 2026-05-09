"""群内 @ Agent 路由(messages.py 短路径)单测 — 纯函数级。"""

from __future__ import annotations

from app.api.messages import _parse_mentions


def test_hint_takes_priority() -> None:
    """前端 popover 选定的 id 优先采纳。"""
    assert _parse_mentions("随便写", ["agent_3"]) == ["agent_3"]


def test_hint_filters_invalid() -> None:
    """非合法 id 直接过滤(防注入)。"""
    assert _parse_mentions("", ["agent_3", "evil_agent"]) == ["agent_3"]


def test_text_fallback_chinese_display_name() -> None:
    assert _parse_mentions("@设计师 来一张", []) == ["agent_3"]


def test_text_fallback_multiple_unique() -> None:
    out = _parse_mentions("@研究员 找资料,@设计师 出图", [])
    assert "agent_1" in out and "agent_3" in out
    assert len(out) == len(set(out))


def test_no_mention_returns_empty() -> None:
    assert _parse_mentions("普通对话", []) == []


def test_hint_dedupe_preserves_order() -> None:
    assert _parse_mentions("", ["agent_3", "agent_1", "agent_3"]) == ["agent_3", "agent_1"]


def test_hr_finance_only_in_hint() -> None:
    """支持 Agent 显示名也能 fallback。"""
    assert _parse_mentions("@HR 加个员工", []) == ["hr"]
    assert _parse_mentions("@财务经理 我的额度", []) == ["finance_manager"]
