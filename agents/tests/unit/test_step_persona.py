"""StepPersona 单元测试(ADR-021)。

覆盖:
- 注册表查找 / fallback default
- ENABLE_STEP_PERSONA=false → 强制 default
- extract_planner_meta / resolve_step_persona_for_task / resolve_budget_tokens
- filter_mcp_uris_by_persona — allowed / denied / 同时
- 关键 personas(critic / researcher / fact_checker)的属性正确性
"""

from __future__ import annotations

import importlib

import pytest

from agents._common.step_persona import (
    StepPersona,
    extract_planner_meta,
    filter_mcp_uris_by_persona,
    get_step_persona,
    list_personas,
    register_persona,
    resolve_budget_tokens,
    resolve_step_persona_for_task,
)


# ─── 注册表查找 ───
def test_get_step_persona_default() -> None:
    p = get_step_persona(None)
    assert p.name == "default"
    p = get_step_persona("")
    assert p.name == "default"
    p = get_step_persona("nonexistent-persona")
    assert p.name == "default"


def test_get_step_persona_known() -> None:
    p = get_step_persona("researcher")
    assert p.name == "researcher"
    assert p.readonly is True
    assert any("search" in x for x in p.allowed_pattern)


def test_get_step_persona_case_insensitive() -> None:
    assert get_step_persona("CRITIC").name == "critic"
    assert get_step_persona(" Critic ").name == "critic"


def test_critic_persona_constraints() -> None:
    p = get_step_persona("critic")
    assert p.readonly is True
    assert p.require_structured_output is True
    assert p.forced_artifact_type == "structured"
    assert p.temperature == 0.1
    # 黑名单覆盖所有 MCP
    assert "mcp://*" in p.denied_pattern


def test_fact_checker_only_allows_search() -> None:
    p = get_step_persona("fact_checker")
    assert any("search" in pat for pat in p.allowed_pattern)
    # 不允许 image / video / audio 工具
    kept, dropped = filter_mcp_uris_by_persona(
        ["mcp://search/web_search", "mcp://image_tools/quality_check"], p
    )
    assert "mcp://search/web_search" in kept
    assert "mcp://image_tools/quality_check" in dropped


def test_list_personas_includes_core() -> None:
    names = set(list_personas())
    assert {"default", "researcher", "critic", "fact_checker", "art_director"} <= names


# ─── flag off ───
def test_disabled_via_env(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_STEP_PERSONA", "false")
    import agents._common.step_persona as sp

    importlib.reload(sp)
    # reload 后 critic 应被强制 fallback 到 default
    assert sp.get_step_persona("critic").name == "default"
    # 恢复
    monkeypatch.setenv("ENABLE_STEP_PERSONA", "true")
    importlib.reload(sp)


# ─── _planner 元信息提取 ───
def test_extract_planner_meta_handles_none() -> None:
    assert extract_planner_meta(None) == {}
    assert extract_planner_meta({}) == {}
    assert extract_planner_meta({"_planner": "not-a-dict"}) == {}


def test_extract_planner_meta_returns_copy() -> None:
    src = {"_planner": {"persona": "critic", "budget_tokens": 4000}}
    meta = extract_planner_meta(src)
    assert meta == {"persona": "critic", "budget_tokens": 4000}
    # 修改返回值不影响源
    meta["persona"] = "x"
    assert src["_planner"]["persona"] == "critic"


def test_resolve_step_persona_for_task() -> None:
    p = resolve_step_persona_for_task({"_planner": {"persona": "researcher"}})
    assert p.name == "researcher"
    p = resolve_step_persona_for_task({"_planner": {"persona": "unknown"}})
    assert p.name == "default"
    p = resolve_step_persona_for_task(None)
    assert p.name == "default"


# ─── budget_tokens ───
def test_resolve_budget_uses_planner_value() -> None:
    n = resolve_budget_tokens({"_planner": {"budget_tokens": 8000}}, default=2000)
    assert n == 8000


def test_resolve_budget_clamps_hard_cap() -> None:
    """budget_tokens 超过硬上限 → 被裁剪。"""
    n = resolve_budget_tokens({"_planner": {"budget_tokens": 99_999}}, default=2000)
    assert n == 32000  # STEP_PERSONA_MAX_BUDGET_TOKENS


def test_resolve_budget_falls_back_on_missing() -> None:
    assert resolve_budget_tokens({}, default=1234) == 1234
    assert resolve_budget_tokens(None, default=1234) == 1234


def test_resolve_budget_falls_back_on_invalid() -> None:
    assert resolve_budget_tokens({"_planner": {"budget_tokens": "bad"}}, default=500) == 500
    assert resolve_budget_tokens({"_planner": {"budget_tokens": -10}}, default=500) == 500
    assert resolve_budget_tokens({"_planner": {"budget_tokens": 0}}, default=500) == 500


def test_resolve_budget_no_default() -> None:
    assert resolve_budget_tokens({}, default=None) is None
    assert resolve_budget_tokens({"_planner": {"budget_tokens": 100}}, default=None) == 100


# ─── 工具白名单过滤 ───
def test_filter_empty_allowed_means_no_restriction() -> None:
    p = StepPersona(name="x", allowed_pattern=(), denied_pattern=())
    kept, dropped = filter_mcp_uris_by_persona(
        ["mcp://search/web_search", "mcp://image_tools/x"], p
    )
    assert len(kept) == 2
    assert dropped == []


def test_filter_allowed_only() -> None:
    p = StepPersona(name="x", allowed_pattern=("mcp://search/*",))
    kept, dropped = filter_mcp_uris_by_persona(
        ["mcp://search/web_search", "mcp://image_tools/x"], p
    )
    assert kept == ["mcp://search/web_search"]
    assert dropped == ["mcp://image_tools/x"]


def test_filter_denied_priority() -> None:
    """denied 优先于 allowed。"""
    p = StepPersona(
        name="x",
        allowed_pattern=("mcp://search/*",),
        denied_pattern=("mcp://search/web_fetch",),
    )
    kept, dropped = filter_mcp_uris_by_persona(
        ["mcp://search/web_search", "mcp://search/web_fetch"], p
    )
    assert kept == ["mcp://search/web_search"]
    assert dropped == ["mcp://search/web_fetch"]


def test_filter_critic_denies_all_mcp() -> None:
    p = get_step_persona("critic")
    kept, dropped = filter_mcp_uris_by_persona(
        ["mcp://search/web_search", "mcp://image_tools/quality_check"], p
    )
    assert kept == []
    assert len(dropped) == 2


def test_filter_skips_invalid() -> None:
    p = StepPersona(name="x", allowed_pattern=("*",))
    kept, dropped = filter_mcp_uris_by_persona(
        ["", "  ", "mcp://search/x"], p  # type: ignore[list-item]
    )
    assert kept == ["mcp://search/x"]


# ─── register_persona ───
def test_register_collision_raises() -> None:
    with pytest.raises(ValueError):
        register_persona(StepPersona(name="critic"))


def test_register_with_override(monkeypatch) -> None:
    custom = StepPersona(name="my-test-persona", addendum="hi")
    register_persona(custom)
    assert get_step_persona("my-test-persona").addendum == "hi"
    # 重复注册 + override
    register_persona(StepPersona(name="my-test-persona", addendum="updated"), override=True)
    assert get_step_persona("my-test-persona").addendum == "updated"
