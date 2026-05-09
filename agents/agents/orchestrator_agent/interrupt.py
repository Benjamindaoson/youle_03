"""子模块 6:中断处理器。

V1 必做 7 类(铁律 21):
- A 补充信息
- B 微调当前
- E 暂停
- F 取消
- G 闲聊
- H 反馈
- I 用户主动切换模式(v4 新)

V2 推迟:C 回滚 / D 改方向。
"""

from __future__ import annotations

import json
from typing import Any, Literal

import structlog
from pydantic import BaseModel

from app.config.prompts import ORCHESTRATOR_INTERRUPT_PROMPT
from app.router import complete

log = structlog.get_logger(__name__)

InterruptClass = Literal["A", "B", "C", "D", "E", "F", "G", "H", "I"]
V1_CLASSES: set[str] = {"A", "B", "E", "F", "G", "H", "I"}


class InterruptClassification(BaseModel):
    interrupt_class: InterruptClass
    reason: str = ""
    action_required: str = ""


async def classify_interrupt(
    *, message: str, current_task_state: dict[str, Any]
) -> InterruptClassification:
    resp = await complete(
        task_type="interrupt_classification",
        messages=[
            {"role": "system", "content": ORCHESTRATOR_INTERRUPT_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {"message": message, "state": current_task_state}, ensure_ascii=False
                ),
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    try:
        data = json.loads(resp.content)
    except json.JSONDecodeError:
        data = {"interrupt_class": "G"}  # 默认归为闲聊
    return InterruptClassification.model_validate(data)


InterruptAction = Literal[
    "merge_brief",       # A 补充信息  → 合并到 brief,继续等待澄清
    "rerun_step",        # B 微调当前  → 把当前 step 标 pending 重派
    "pause_task",        # E 暂停      → 任务挂起
    "cancel_task",       # F 取消      → 任务终止
    "chat_reply",        # G 闲聊      → 主编排走聊天 LLM
    "store_feedback",    # H 反馈      → 落 prompt_improvement_candidates
    "switch_mode",       # I 切换模式  → mode_manager 处理
    "v2_deferred",       # C/D — V1 不实现，由调用方返回固定响应
]


# V1 派发表(铁律 21):每个中断类别 → 一个动作 token
_DISPATCH: dict[str, InterruptAction] = {
    "A": "merge_brief",
    "B": "rerun_step",
    "E": "pause_task",
    "F": "cancel_task",
    "G": "chat_reply",
    "H": "store_feedback",
    "I": "switch_mode",
}


async def handle_interrupt(
    classification: InterruptClassification, *, task_state: dict[str, Any]
) -> InterruptAction:
    """分发中断到具体动作 token。

    返回 action token,由调用方(API / 主编排)按 token 调具体 handler:
      - merge_brief / rerun_step → orchestrator.runner
      - pause_task / cancel_task → task service
      - chat_reply → 走聊天 LLM
      - store_feedback → flywheel.record_feedback
      - switch_mode → orchestrator.mode_manager
    """
    if classification.interrupt_class in {"C", "D"}:
        log.info(
            "interrupt.v2_deferred",
            cls=classification.interrupt_class,
            reason=classification.reason,
        )
        return "v2_deferred"
    action = _DISPATCH[classification.interrupt_class]
    log.info(
        "interrupt.handle",
        cls=classification.interrupt_class,
        action=action,
        reason=classification.reason,
    )
    return action
