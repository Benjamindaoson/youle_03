"""Agent 1 扩展 handlers — V1.5 真实现(PM override 铁律 11,全量代码实现)。

每个 handler 走 LiteLLM(铁律 7)+ task-specific system prompt + 结构化输出。
- structured_writing → JSON Schema 提示词 + 解析
- summarization → 抽取式 / 生成式 选项
- analysis → 论点 / 论据 / 结论 三段输出
- translation → 双向 + 术语表
- polish → 风格化(精简 / 学术 / 营销)
"""

from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

import structlog

from agents._common import llm
from agents._common.oss_writer import put_text
from agents._common.protocol import AgentResult, AgentTask, ArtifactRef

log = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────
# 1. structured_writing — JSON 输出
# ─────────────────────────────────────────────────────────────────
_STRUCTURED_SYSTEM = """\
你是结构化写作师。严格按用户给的 JSON Schema 输出,字段名用 snake_case。
不要输出 ```json 围栏,直接输出可解析的 JSON。
缺字段时填合理默认值,不要返回空字符串。
"""


async def structured_writing_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()
    prompt = task.inputs.get("_prompt") or task.inputs.get("prompt", "")
    schema = task.parameters.get("schema") or task.inputs.get("schema") or {}
    if not prompt:
        return _fail(task, "missing_prompt")
    user_msg = prompt
    if schema:
        user_msg = f"{prompt}\n\n请按以下 JSON Schema 输出:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
    try:
        resp = await llm.complete(
            task_type=task.task_type,
            messages=[
                {"role": "system", "content": _STRUCTURED_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            routing_hints=task.routing_hints,
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=task.parameters.get("max_tokens", 1500),
        )
        # 验 JSON
        try:
            parsed = json.loads(resp.content)
            valid_json = True
        except Exception:
            parsed = None
            valid_json = False
        oss_ref = await put_text(
            key=f"artifacts/{task.task_id}/{task.step_id}.json",
            content=resp.content,
            content_type="application/json",
        )
        return _ok(
            task,
            artifact_type="json",
            reference=oss_ref,
            metadata={
                "model": resp.model,
                "valid_json": valid_json,
                "schema_keys": list(schema.keys()) if schema else [],
                "fields": list(parsed.keys()) if isinstance(parsed, dict) else [],
            },
            cost_usd=resp.cost_usd,
            model=resp.model,
            t0=t0,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("structured_writing.failed", err=str(e))
        return _fail(task, "llm_error", error=str(e)[:200])


# ─────────────────────────────────────────────────────────────────
# 2. summarization — extractive / generative
# ─────────────────────────────────────────────────────────────────
_SUMMARIZATION_PROMPTS = {
    "extractive": (
        "你是摘要师。从原文中**抽取**(不改写)最关键的 3-5 句话作为摘要。"
        "保留原文用词,按重要性排序。"
    ),
    "generative": (
        "你是摘要师。先列 3-5 个要点(每条 ≤ 30 字),"
        "再给一段不超 200 字的总结。允许改写,但保持原意。"
    ),
    "tldr": "你是摘要师。给一句 ≤ 50 字的 TL;DR。",
}


async def summarization_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()
    prompt = task.inputs.get("_prompt") or task.inputs.get("text") or task.inputs.get("prompt", "")
    style = task.parameters.get("style", "generative")
    if not prompt:
        return _fail(task, "missing_text")
    system = _SUMMARIZATION_PROMPTS.get(style, _SUMMARIZATION_PROMPTS["generative"])
    try:
        resp = await llm.complete(
            task_type="summarization",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            routing_hints=task.routing_hints,
            temperature=0.4,
            max_tokens=task.parameters.get("max_tokens", 600),
        )
        oss_ref = await put_text(
            key=f"artifacts/{task.task_id}/{task.step_id}.txt", content=resp.content
        )
        return _ok(
            task,
            artifact_type="text",
            reference=oss_ref,
            metadata={
                "model": resp.model,
                "style": style,
                "input_chars": len(prompt),
                "output_chars": len(resp.content),
                "compression": round(len(resp.content) / max(len(prompt), 1), 3),
            },
            cost_usd=resp.cost_usd,
            model=resp.model,
            t0=t0,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("summarization.failed", err=str(e))
        return _fail(task, "llm_error", error=str(e)[:200])


# ─────────────────────────────────────────────────────────────────
# 3. analysis — 论点 / 论据 / 结论
# ─────────────────────────────────────────────────────────────────
_ANALYSIS_SYSTEM = """\
你是分析师。从给定材料中提炼:
1. 核心论点(claims)— 列 2-5 个主张
2. 关键论据(evidence)— 每个论点配 1-3 条事实/数据/例子
3. 结论(conclusion)— 一段 100 字内的结论

按 JSON 输出,字段:claims(list[str])、evidence(list[list[str]])、conclusion(str)。
"""


async def analysis_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()
    prompt = task.inputs.get("_prompt") or task.inputs.get("text") or task.inputs.get("prompt", "")
    if not prompt:
        return _fail(task, "missing_text")
    try:
        resp = await llm.complete(
            task_type="analysis",
            messages=[
                {"role": "system", "content": _ANALYSIS_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            routing_hints=task.routing_hints,
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=task.parameters.get("max_tokens", 1200),
        )
        valid_json = True
        try:
            data = json.loads(resp.content)
            n_claims = len(data.get("claims", [])) if isinstance(data, dict) else 0
        except Exception:
            valid_json = False
            n_claims = 0
        oss_ref = await put_text(
            key=f"artifacts/{task.task_id}/{task.step_id}.json",
            content=resp.content,
            content_type="application/json",
        )
        return _ok(
            task,
            artifact_type="json",
            reference=oss_ref,
            metadata={
                "model": resp.model,
                "valid_json": valid_json,
                "claims_count": n_claims,
            },
            cost_usd=resp.cost_usd,
            model=resp.model,
            t0=t0,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("analysis.failed", err=str(e))
        return _fail(task, "llm_error", error=str(e)[:200])


# ─────────────────────────────────────────────────────────────────
# 4. translation — 双向 + 术语表
# ─────────────────────────────────────────────────────────────────
async def translation_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()
    prompt = task.inputs.get("_prompt") or task.inputs.get("text") or task.inputs.get("prompt", "")
    direction = task.parameters.get("direction", "auto")  # zh2en / en2zh / auto
    glossary: dict[str, str] = task.parameters.get("glossary") or {}
    if not prompt:
        return _fail(task, "missing_text")

    direction_hint = {
        "zh2en": "把中文翻成英文",
        "en2zh": "把英文翻成中文",
        "auto": "自动检测语言并翻成另一种(中 ↔ 英)",
    }.get(direction, "自动翻译")

    glossary_block = ""
    if glossary:
        terms = "\n".join(f"  - {src} → {dst}" for src, dst in glossary.items())
        glossary_block = f"\n\n**术语表(必须严格遵守)**:\n{terms}"

    system = (
        f"你是翻译师。{direction_hint}。"
        f"保持原文格式(段落 / 列表 / 标题),不加解释、不评论。{glossary_block}"
    )
    try:
        resp = await llm.complete(
            task_type="translation",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            routing_hints=task.routing_hints,
            temperature=0.2,
            max_tokens=task.parameters.get("max_tokens", 2000),
        )
        oss_ref = await put_text(
            key=f"artifacts/{task.task_id}/{task.step_id}.txt", content=resp.content
        )
        # 校对术语命中率(简易:看翻译里是否含每个 dst term)
        glossary_hits = (
            sum(1 for dst in glossary.values() if dst in resp.content)
            if glossary
            else 0
        )
        return _ok(
            task,
            artifact_type="text",
            reference=oss_ref,
            metadata={
                "model": resp.model,
                "direction": direction,
                "glossary_size": len(glossary),
                "glossary_hits": glossary_hits,
            },
            cost_usd=resp.cost_usd,
            model=resp.model,
            t0=t0,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("translation.failed", err=str(e))
        return _fail(task, "llm_error", error=str(e)[:200])


# ─────────────────────────────────────────────────────────────────
# 5. polish — 风格化润色
# ─────────────────────────────────────────────────────────────────
_POLISH_PROMPTS = {
    "concise": "你是润色师。改简洁,删冗余,保留原意,不加新内容。每句话至少削减 20%。",
    "academic": "你是润色师。改成学术写作风格,严谨、客观、被动句多,术语规范。",
    "marketing": "你是润色师。改成营销文案风格,有钩子、有情绪、行动号召明确。",
    "fluent": "你是润色师。改通顺、改自然,语序流畅。保持原意,不加新内容。",
}


async def polish_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()
    prompt = task.inputs.get("_prompt") or task.inputs.get("text") or task.inputs.get("prompt", "")
    style = task.parameters.get("style", "fluent")
    if not prompt:
        return _fail(task, "missing_text")
    system = _POLISH_PROMPTS.get(style, _POLISH_PROMPTS["fluent"])
    try:
        resp = await llm.complete(
            task_type="polish",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            routing_hints=task.routing_hints,
            temperature=0.5,
            max_tokens=task.parameters.get("max_tokens", 1500),
        )
        oss_ref = await put_text(
            key=f"artifacts/{task.task_id}/{task.step_id}.txt", content=resp.content
        )
        return _ok(
            task,
            artifact_type="text",
            reference=oss_ref,
            metadata={
                "model": resp.model,
                "style": style,
                "input_chars": len(prompt),
                "output_chars": len(resp.content),
                "ratio": round(len(resp.content) / max(len(prompt), 1), 3),
            },
            cost_usd=resp.cost_usd,
            model=resp.model,
            t0=t0,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("polish.failed", err=str(e))
        return _fail(task, "llm_error", error=str(e)[:200])


# ─────────────────────────────────────────────────────────────────
# 公共构造
# ─────────────────────────────────────────────────────────────────
def _ok(
    task: AgentTask,
    *,
    artifact_type: str,
    reference: str,
    metadata: dict[str, Any],
    cost_usd: float | None,
    model: str | None,
    t0: float,
) -> AgentResult:
    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="completed",
        output=ArtifactRef(
            artifact_id=uuid4(),
            type=artifact_type,
            reference=reference,
            extra_metadata=metadata,
        ),
        cost_usd=cost_usd,
        duration_ms=int((time.monotonic() - t0) * 1000),
        model_used=model,
    )


def _fail(task: AgentTask, reason: str, **extra: Any) -> AgentResult:
    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="failed",
        error_detail={"reason": reason, **extra},
    )
