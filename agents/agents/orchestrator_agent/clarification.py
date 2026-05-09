"""子模块 4:澄清生成器(铁律 6:永远选择题,≤5 轮)。

4 种形式:single_select / multi_select / image_compare / version_compare / image_upload
多轮状态由调用方(messages.py)用 Redis key `clarif:{conv_id}` 维护。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ClarificationForm = Literal["single_select", "multi_select", "image_compare", "version_compare", "image_upload"]

MAX_CLARIFICATION_ROUNDS = 5  # 铁律 6:澄清 ≤ 5 轮


class Clarification(BaseModel):
    field: str
    form: ClarificationForm
    question: str
    options: list[Any] = Field(default_factory=list)
    default: Any | None = None
    timeout_seconds: int = 60
    round_number: int = 0        # 当前是第几轮(0-based),供前端进度展示
    total_missing: int = 0       # 还剩几个缺失字段,供前端展示进度


def generate_clarification(
    missing_fields: list[dict[str, Any]],
    *,
    round_number: int = 0,
) -> Clarification | None:
    """每轮针对一个缺失字段生成澄清;返回 None 表示无需澄清。

    round_number 0-based:第 0 轮问 missing_fields[0],第 1 轮问 missing_fields[1],…
    超出列表长度时循环到最后一个字段(防越界)。
    """
    if not missing_fields:
        return None

    idx = min(round_number, len(missing_fields) - 1)
    field = missing_fields[idx]
    form: ClarificationForm = field.get("clarification_form", "single_select")

    question = field.get("question") or f"请选择{field['name']}"

    return Clarification(
        field=field["name"],
        form=form,
        question=question,
        options=field.get("options", []),
        default=field.get("default"),
        timeout_seconds=field.get("timeout_seconds", 60),
        round_number=round_number,
        total_missing=len(missing_fields),
    )
