"""Agent 3 style_extract — 从参考图提取品牌风格指引(多模态 vision)。

设计:
- 走 LiteLLM vision 模型(claude-sonnet-vision / gpt-5-vision)
- 输出结构化 JSON:调色板/构图/字体/情绪/prompt_inject
- prompt_inject 字段可直接注入 batch_generate 的 image_specs[i].prompt
- 落 OSS,extra_metadata 暴露 prompt_inject 供主编排直接读取

关键约定:
- 缺少 image_ref 直接 fast-fail,不会用空图调 vision 浪费 token
- LLM 返回非 JSON 或 schema 不符 → 返回 status="failed",上游决策重试
- emit(flywheel 信号)失败不影响主结果,通过 try/except 隔离
- OSS key 不带时间戳,同 step 重试会覆盖(幂等设计)
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from uuid import uuid4

import structlog

from agents._common import llm
from agents._common.flywheel_emitter import emit
from agents._common.oss_writer import put_json
from agents._common.prompts import STYLE_EXTRACT_SYSTEM
from agents._common.protocol import AgentResult, AgentTask, ArtifactRef

log = structlog.get_logger(__name__)

AGENT_ID = "agent_3"
TASK_TYPE = "style_extract"

# vision 调用单次超时上界,防止长尾撑爆 worker 并发
_LLM_TIMEOUT_SEC = 60.0
# emit / 日志中的字段截断长度
_PROMPT_INJECT_EMIT_MAX = 120
_PROMPT_INJECT_METADATA_MAX = 200
# style_guide 的字段集合(用于空模板和校验)
_STYLE_GUIDE_FIELDS = (
    "palette", "composition", "typography", "mood",
    "lighting", "do", "dont", "prompt_inject",
)


def _empty_style_guide() -> dict[str, Any]:
    """构造空 style_guide(用于解析失败时的 OSS 占位)。"""
    return {
        "palette": [],
        "composition": "",
        "typography": "",
        "mood": [],
        "lighting": "",
        "do": [],
        "dont": [],
        "prompt_inject": "",
    }


def _resolve_image_ref(task: AgentTask) -> str:
    """从 inputs / parameters 多个候选字段中解析 image_ref。

    历史原因支持 4 个 key,最终应收敛到 inputs["image_ref"];
    使用旧 key 时打 deprecation warning,便于追踪上游迁移进度。
    """
    canonical = task.inputs.get("image_ref")
    if canonical:
        return str(canonical)

    for legacy_key, source in (
        ("reference", task.inputs),
        ("ref", task.inputs),
        ("image_ref", task.parameters),
    ):
        val = source.get(legacy_key)
        if val:
            log.warning(
                "style_extract.legacy_image_ref_key",
                used_key=legacy_key,
                hint="migrate to inputs['image_ref']",
            )
            return str(val)

    return ""


def _parse_style_guide(content: Any) -> dict[str, Any] | None:
    """解析 LLM 响应为 style_guide dict;失败返回 None。"""
    if not isinstance(content, str):
        return None
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _safe_str_field(d: dict[str, Any], key: str, max_len: int) -> str:
    """从 style_guide 安全取字符串字段并截断,处理类型偏离。"""
    val = d.get(key, "")
    if not isinstance(val, str):
        val = str(val)
    return val[:max_len]


def _safe_list_field(d: dict[str, Any], key: str) -> list[Any]:
    """从 style_guide 安全取列表字段,处理类型偏离。"""
    val = d.get(key, [])
    if not isinstance(val, list):
        return []
    return val


async def _emit_signal_safe(payload: dict[str, Any]) -> None:
    """flywheel emit 不影响主结果;失败仅记日志。"""
    try:
        await emit(signal_type="preference", payload=payload)
    except Exception as e:
        log.warning(
            "style_extract.emit_failed",
            err=str(e)[:300],
            task_id=payload.get("task_id"),
        )


def _failure_result(
    task: AgentTask,
    *,
    reason: str,
    duration_ms: int,
    model_used: str | None = None,
    cost_usd: float = 0.0,
) -> AgentResult:
    """构造 failed 结果,把失败原因塞到 metadata 让上游可读。"""
    log.warning(
        "style_extract.failed",
        agent=AGENT_ID,
        task_id=str(task.task_id),
        step_id=task.step_id,
        reason=reason,
    )
    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="failed",
        output=ArtifactRef(
            artifact_id=uuid4(),
            type="structured",
            reference="",
            extra_metadata={"failure_reason": reason},
        ),
        cost_usd=cost_usd,
        duration_ms=duration_ms,
        model_used=model_used or "",
    )


async def style_extract_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()

    # —— 1. 输入校验:无图直接 fast-fail ——
    image_ref = _resolve_image_ref(task)
    if not image_ref:
        return _failure_result(
            task,
            reason="missing_image_ref",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    style_pref = (
        task.inputs.get("style_pref")
        or task.parameters.get("style_pref", "")
    )

    # —— 2. 构造 vision 消息 ——
    user_text = "请从这张图提取风格指引,严格按 JSON 格式输出。"
    if style_pref:
        user_text += f"\n用户偏好风格: {style_pref}"

    messages = [
        {"role": "system", "content": STYLE_EXTRACT_SYSTEM},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": image_ref}},
            ],
        },
    ]

    # —— 3. 调用 LLM(带超时上界)——
    try:
        async with asyncio.timeout(_LLM_TIMEOUT_SEC):
            resp = await llm.complete(
                task_type=TASK_TYPE,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.2,
                routing_hints=task.routing_hints,
            )
    except asyncio.TimeoutError:
        return _failure_result(
            task,
            reason=f"llm_timeout_{int(_LLM_TIMEOUT_SEC)}s",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    # —— 4. 解析与校验 ——
    style_guide = _parse_style_guide(resp.content)
    if style_guide is None:
        # 解析失败仍写一份占位到 OSS,方便归因(知道走到哪一步坏的)
        empty = _empty_style_guide()
        empty["_parse_failed"] = True
        try:
            await put_json(
                key=f"artifacts/{task.task_id}/{task.step_id}.json",
                payload=empty,
            )
        except Exception as e:
            log.warning("style_extract.oss_write_failed_on_parse_error", err=str(e)[:300])

        return _failure_result(
            task,
            reason="llm_response_not_valid_json",
            duration_ms=int((time.monotonic() - t0) * 1000),
            model_used=resp.model,
            cost_usd=resp.cost_usd,
        )

    # —— 5. 落 OSS ——
    oss_ref = await put_json(
        key=f"artifacts/{task.task_id}/{task.step_id}.json",
        payload=style_guide,
    )

    # —— 6. 飞轮信号(失败不影响主结果)——
    prompt_inject_for_emit = _safe_str_field(
        style_guide, "prompt_inject", _PROMPT_INJECT_EMIT_MAX
    )
    await _emit_signal_safe(
        {
            "task_id": str(task.task_id),
            "step_id": task.step_id,
            "agent_id": AGENT_ID,
            "task_type": TASK_TYPE,
            "mood": _safe_list_field(style_guide, "mood"),
            "prompt_inject": prompt_inject_for_emit,
        }
    )

    # —— 7. 返回结果 ——
    duration_ms = int((time.monotonic() - t0) * 1000)
    log.info(
        "style_extract.ok",
        agent=AGENT_ID,
        task_id=str(task.task_id),
        step_id=task.step_id,
        model=resp.model,
        duration_ms=duration_ms,
        has_prompt_inject=bool(prompt_inject_for_emit),
    )

    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="completed",
        output=ArtifactRef(
            artifact_id=uuid4(),
            type="structured",
            reference=oss_ref,
            extra_metadata={
                "prompt_inject": _safe_str_field(
                    style_guide, "prompt_inject", _PROMPT_INJECT_METADATA_MAX
                ),
                "mood": _safe_list_field(style_guide, "mood"),
                "model": resp.model,
            },
        ),
        cost_usd=resp.cost_usd,
        duration_ms=duration_ms,
        model_used=resp.model,
    )