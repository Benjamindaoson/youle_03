"""Agent 3 image_quality_check — 多模态 vision 批量评分 + 自动过滤。

设计:
- 支持单张 image_ref 或批量 image_refs
- 8 维度评分(各 0-1),加权汇总为总分
- auto_filter=True:过滤低于 threshold(默认 0.65)的图,返回 filtered_refs
- 产出结构化 JSON 报告落 OSS,extra_metadata 暴露 avg_score/pass 率
- asyncio.gather 并发调用,不串行等待
"""

from __future__ import annotations

import asyncio
import json
import time
from uuid import uuid4

import structlog

from agents._common import llm
from agents._common.flywheel_emitter import emit
from agents._common.oss_writer import put_json
from agents._common.prompts import IMAGE_QUALITY_CHECK_SYSTEM
from agents._common.protocol import AgentResult, AgentTask, ArtifactRef

log = structlog.get_logger(__name__)

_DEFAULT_THRESHOLD = 0.65


async def _check_one(
    image_ref: str,
    routing_hints: dict | None,
) -> dict:
    """对单张图做多模态质检,返回 report dict。"""
    resp = await llm.complete(
        task_type="image_quality_check",
        messages=[
            {"role": "system", "content": IMAGE_QUALITY_CHECK_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请评估这张图的质量,严格按 JSON 格式输出。"},
                    {"type": "image_url", "image_url": {"url": str(image_ref)}},
                ],
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        routing_hints=routing_hints,
    )

    try:
        report = json.loads(resp.content)
    except (json.JSONDecodeError, ValueError):
        log.warning("image_quality_check.parse_failed", ref=str(image_ref)[:60])
        report = {
            "score": 0.5,
            "dimensions": {},
            "issues": ["json_parse_failed"],
            "suggestion": "",
        }

    report["image_ref"] = image_ref
    report["model"] = resp.model
    # 保证 score 是 float
    try:
        report["score"] = float(report.get("score", 0.5))
    except (TypeError, ValueError):
        report["score"] = 0.5
    return report


async def image_quality_check_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()

    # 支持批量 image_refs 或单张 image_ref/reference
    image_refs: list[str] = list(
        task.inputs.get("image_refs")
        or task.parameters.get("image_refs")
        or []
    )
    if not image_refs:
        single = (
            task.inputs.get("image_ref")
            or task.inputs.get("reference")
            or task.inputs.get("_prompt", "")
        )
        if single:
            image_refs = [single]

    if not image_refs:
        return AgentResult(
            task_id=task.task_id,
            step_id=task.step_id,
            status="failed",
            error_detail={"reason": "no_image_refs"},
        )

    threshold = float(task.parameters.get("threshold", _DEFAULT_THRESHOLD))
    auto_filter = bool(task.parameters.get("auto_filter", False))

    # 并发质检
    reports: list[dict] = list(
        await asyncio.gather(
            *(_check_one(ref, task.routing_hints) for ref in image_refs)
        )
    )

    # pass/fail 标注
    for r in reports:
        r["pass"] = r["score"] >= threshold

    passing = [r for r in reports if r["pass"]]
    filtered_refs = [r["image_ref"] for r in (passing if auto_filter else reports)]
    avg_score = round(sum(r["score"] for r in reports) / len(reports), 3)

    batch_report = {
        "total": len(reports),
        "passed": len(passing),
        "failed": len(reports) - len(passing),
        "avg_score": avg_score,
        "threshold": threshold,
        "auto_filter": auto_filter,
        "filtered_refs": filtered_refs,
        "reports": reports,
    }

    oss_ref = await put_json(
        key=f"artifacts/{task.task_id}/{task.step_id}.json",
        payload=batch_report,
    )

    await emit(
        signal_type="trace",
        payload={
            "task_id": str(task.task_id),
            "step_id": task.step_id,
            "agent_id": "agent_3",
            "task_type": "image_quality_check",
            "total": len(reports),
            "passed": len(passing),
            "avg_score": avg_score,
            "threshold": threshold,
        },
    )

    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="completed",
        output=ArtifactRef(
            artifact_id=uuid4(),
            type="quality_report",
            reference=oss_ref,
            extra_metadata={
                "total": len(reports),
                "passed": len(passing),
                "avg_score": avg_score,
                "filtered_refs": filtered_refs,
            },
        ),
        duration_ms=int((time.monotonic() - t0) * 1000),
    )
