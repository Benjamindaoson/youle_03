"""主编排子模块 3 — 输入校验器单测(纯程序,不调 LLM)。"""

from __future__ import annotations

from agents.orchestrator_agent.input_validator import validate_inputs


def test_all_filled() -> None:
    schema = [
        {"name": "年份", "type": "number", "required": True, "default": 2026},
        {"name": "时长", "type": "enum", "required": False, "default": "60s"},
    ]
    res = validate_inputs(inputs_schema=schema, collected_fields={"年份": 2026, "时长": "60s"})
    assert res.is_complete
    assert res.filled_fields == {"年份": 2026, "时长": "60s"}


def test_missing_required() -> None:
    schema = [
        {"name": "主题", "type": "enum", "required": True, "options": ["城市漫游", "投资理财"]},
    ]
    res = validate_inputs(inputs_schema=schema, collected_fields={})
    assert not res.is_complete
    assert len(res.missing_fields) == 1
    assert res.missing_fields[0]["name"] == "主题"


def test_use_default_for_optional() -> None:
    schema = [{"name": "时长", "type": "enum", "required": False, "default": "60s"}]
    res = validate_inputs(inputs_schema=schema, collected_fields={})
    assert res.filled_fields["时长"] == "60s"
    assert res.is_complete


def test_user_preference_high_confidence() -> None:
    schema = [{"name": "受众", "type": "enum", "required": True}]
    prefs = {"受众": {"value": "城市老人", "confidence": 1.0}}
    res = validate_inputs(
        inputs_schema=schema, collected_fields={}, user_preferences=prefs
    )
    assert res.filled_fields["受众"] == "城市老人"
    assert res.is_complete


def test_user_preference_low_confidence_skipped() -> None:
    schema = [{"name": "受众", "type": "enum", "required": True}]
    prefs = {"受众": {"value": "城市老人", "confidence": 0.4}}
    res = validate_inputs(
        inputs_schema=schema, collected_fields={}, user_preferences=prefs
    )
    assert not res.is_complete
