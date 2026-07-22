"""子模块 1:意图理解器。

输入:user_message + 最近对话历史 + 会话上下文
输出:Intent JSON {intent_type, domain, scenario, entities, confidence}
模型:deepseek-v4-flash(L1)

详见 docs/2_工程实现/主编排 Agent 实现指南.md §1
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field

from app.config.prompts import ORCHESTRATOR_INTENT_PROMPT
from app.router import complete
from app.services.metrics import record_intent_latency

log = structlog.get_logger(__name__)

IntentType = Literal[
    "task_request",
    "chitchat",
    "clarification_answer",
    "interrupt",
    "mode_switch",
    "team_management",
    "quota_query",
]


class Intent(BaseModel):
    intent_type: IntentType
    domain: Literal["text", "image", "video", "document", "mixed", "none"] = "none"
    scenario: str | None = None
    entities: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0


_EXPLICIT_ENTITY_NAMES = (
    "主题",
    "风格",
    "受众",
    "时长",
    "平台",
    "开头钩子",
    "商品图",
    "卖点",
    "风格基调",
    "字数",
    "页数",
    "风格关键词",
)
_EXPLICIT_ENTITY_RE = re.compile(
    rf"(?:^|[。.!！]\s*)({'|'.join(_EXPLICIT_ENTITY_NAMES)})\s*[：:]\s*(.+)$"
)


def _extract_explicit_entities(user_message: str) -> dict[str, str]:
    """Extract user-labelled fields without spending another model call."""
    entities: dict[str, str] = {}
    for segment in re.split(r"[；;\n]+", user_message):
        match = _EXPLICIT_ENTITY_RE.search(segment.strip())
        if not match:
            continue
        value = match.group(2).strip().rstrip("。.!！ ")
        if value:
            entities[match.group(1)] = value
    return entities


async def understand_intent(
    *,
    user_message: str,
    recent_history: list[dict[str, str]] | None = None,
    conversation_context: dict[str, Any] | None = None,
) -> Intent:
    history = recent_history or []
    context_blob = dict(conversation_context or {})

    # 若调用方传入了会话摘要,前置注入让 LLM 了解对话背景
    memory_summary = context_blob.pop("memory_summary", "") if isinstance(context_blob, dict) else ""
    system_content = ORCHESTRATOR_INTENT_PROMPT
    if memory_summary:
        system_content = (
            f"【近期会话与任务记忆】\n{memory_summary[:2200]}\n\n"
            + system_content
        )

    messages = [
        {"role": "system", "content": system_content},
        *history,
        {
            "role": "user",
            "content": json.dumps(
                {"message": user_message, "context": context_blob}, ensure_ascii=False
            ),
        },
    ]
    t0 = time.monotonic()
    resp = await complete(
        task_type="intent_understanding",
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    record_intent_latency(time.monotonic() - t0)
    try:
        data = json.loads(resp.content)
    except json.JSONDecodeError:
        log.warning("intent.parse_failed", content=resp.content[:200])
        data = {"intent_type": "chitchat", "confidence": 0.0}
    data["entities"] = {
        **(data.get("entities") or {}),
        **_extract_explicit_entities(user_message),
    }
    return Intent.model_validate(data)
