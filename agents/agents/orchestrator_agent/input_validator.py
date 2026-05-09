"""子模块 3:输入校验器(纯程序,不调 LLM)。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    filled_fields: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[dict[str, Any]] = Field(default_factory=list)
    is_complete: bool = False


def validate_inputs(
    *,
    inputs_schema: list[dict[str, Any]],
    collected_fields: dict[str, Any],
    user_preferences: dict[str, Any] | None = None,
    brief: dict[str, Any] | None = None,
) -> ValidationResult:
    user_preferences = user_preferences or {}
    brief = brief or {}
    brief_fields = brief.get("字段", {})

    filled: dict[str, Any] = {}
    missing: list[dict[str, Any]] = []

    for field_def in inputs_schema:
        name = field_def["name"]
        required = field_def.get("required", False)

        if name in collected_fields:
            filled[name] = collected_fields[name]
            continue
        if name in brief_fields:
            filled[name] = brief_fields[name]
            continue

        # confidence ≥ 1.0 自动套用偏好
        pref = user_preferences.get(name)
        if isinstance(pref, dict) and pref.get("confidence", 0) >= 1.0:
            filled[name] = pref["value"]
            continue

        if "default" in field_def and not required:
            filled[name] = field_def["default"]
            continue

        if required:
            missing.append(field_def)

    return ValidationResult(filled_fields=filled, missing_fields=missing, is_complete=not missing)
