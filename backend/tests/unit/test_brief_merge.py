"""Brief → Skill inputs 字段填充单测。"""

from __future__ import annotations

from app.services.brief_builder import merge_brief_into_skill_inputs


def test_direct_field_match() -> None:
    brief = {"字段": {"年份": 2026, "受众": "城市老人"}}
    schema = [{"name": "年份"}, {"name": "受众"}]
    assert merge_brief_into_skill_inputs(brief=brief, inputs_schema=schema) == {
        "年份": 2026,
        "受众": "城市老人",
    }


def test_alias_match() -> None:
    brief = {"字段": {"年份": 2026}}
    schema = [{"name": "年度"}]
    assert merge_brief_into_skill_inputs(brief=brief, inputs_schema=schema) == {
        "年度": 2026
    }


def test_no_match_returns_empty() -> None:
    brief = {"字段": {"无关字段": "x"}}
    schema = [{"name": "年份"}]
    assert merge_brief_into_skill_inputs(brief=brief, inputs_schema=schema) == {}


def test_partial_fill() -> None:
    brief = {"字段": {"年份": 2026}}
    schema = [{"name": "年份"}, {"name": "受众"}]
    assert merge_brief_into_skill_inputs(brief=brief, inputs_schema=schema) == {
        "年份": 2026
    }


def test_empty_brief_safe() -> None:
    assert merge_brief_into_skill_inputs(brief={}, inputs_schema=[{"name": "年份"}]) == {}
    assert merge_brief_into_skill_inputs(
        brief={"字段": None}, inputs_schema=[]  # type: ignore[arg-type]
    ) == {}
