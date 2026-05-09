"""子模块 7:三模式管理器(v3.0 ADR-014)。

Plan / Ask / Auto 同群内切换 + Brief 持续维护。
铁律 17:不建讨论群/工作群两种独立群。
铁律 20:Plan/Ask 不消耗任务配额,只算 token。
"""

from __future__ import annotations

import json
from typing import Any, Literal

import structlog
from pydantic import BaseModel

from app.config.prompts import (
    ORCHESTRATOR_BRIEF_UPDATE_PROMPT,
    WORK_MODE_SWITCH_PROMPT,
)
from app.router import complete

log = structlog.get_logger(__name__)

WorkMode = Literal["plan", "ask", "auto"]


class ModeSwitchSignal(BaseModel):
    switch_to: WorkMode | None = None
    confidence: float = 0.0


async def detect_mode_switch(
    *, current_mode: WorkMode | None, conversation_name: str, message: str
) -> ModeSwitchSignal:
    """中断 I:用户说"开干"/"等等想想"/"问个问题" → 自动切模式。"""
    resp = await complete(
        task_type="work_mode_switch",
        messages=[
            {
                "role": "system",
                "content": WORK_MODE_SWITCH_PROMPT.format(
                    conversation_name=conversation_name,
                    current_work_mode=current_mode or "none",
                ),
            },
            {"role": "user", "content": message},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    try:
        data = json.loads(resp.content)
    except json.JSONDecodeError:
        return ModeSwitchSignal(switch_to=None, confidence=0.0)
    return ModeSwitchSignal.model_validate(data)


async def update_brief(
    *, current_brief: dict[str, Any], new_messages: list[dict[str, str]]
) -> dict[str, Any]:
    """讨论模式下持续维护 brief(铁律 6:5 秒静默 + 累计 3 条触发)。"""
    resp = await complete(
        task_type="brief_update",
        messages=[
            {
                "role": "system",
                "content": ORCHESTRATOR_BRIEF_UPDATE_PROMPT.format(
                    current_brief=json.dumps(current_brief, ensure_ascii=False),
                    new_messages=json.dumps(new_messages, ensure_ascii=False),
                ),
            }
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    try:
        return json.loads(resp.content)
    except json.JSONDecodeError:
        log.warning("brief.parse_failed")
        return current_brief


def consumes_task_quota(work_mode: WorkMode | None) -> bool:
    """铁律 20:Plan/Ask 不消耗任务配额,只算 token;Auto 才扣任务配额。"""
    return work_mode == "auto"
