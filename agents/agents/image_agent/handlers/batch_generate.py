"""Agent 3 batch_generate — 批量生图:风格锚点 + 并行生成 + manifest 落 OSS。

设计:
- 第 1 张图作为"风格锚点",normalize 后将风格约束注入后续 prompt
- 后续图 asyncio.gather 并行生成(无阻塞等待)
- 全部通过 _normalize_image_artifact 规范化(URL/base64/oss 三类)
- 写 manifest.json 记录所有 ref + metadata
- 支持 ecommerce / default 两种预设风格提示
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import uuid4

import structlog

from agents._common import llm
from agents._common.flywheel_emitter import emit
from agents._common.memory_client import build_pref_context, get_user_prefs
from agents._common.oss_writer import put_json
from agents._common.prompts import IMAGE_GENERATE_SYSTEM
from agents._common.protocol import AgentResult, AgentTask, ArtifactRef
from agents.image_agent.handlers.extras import _normalize_image_artifact

log = structlog.get_logger(__name__)

_SET_TYPE_STYLE_HINTS: dict[str, str] = {
    "ecommerce": (
        "白底留白产品图,主体居中,卖点文字清晰,"
        "电商橙/红点缀,干净专业高转化率"
    ),
    "default": "统一色调和构图风格,保持视觉一致性",
}


async def _gen_one(
    *,
    spec: dict,
    idx: int,
    style_context: str,
    task_id: str,
    step_id: str,
    routing_hints: dict | None,
) -> tuple[str, str, str, list[dict[Any, Any]]]:
    """生成单张图并 normalize,返回 (ref, normalized_via, model, xhs_trail)。"""
    prompt = spec.get("prompt", "")
    full_prompt = f"{style_context}\n{prompt}" if style_context else prompt
    vk = spec.get("xhs_visual_kind")
    trail: list[dict[Any, Any]] = []
    if isinstance(vk, str) and vk:
        from agents.image_agent.xhs_image_router import generate_with_xhs_model_chain

        try:
            resp, trail = await generate_with_xhs_model_chain(
                logical_task_type="xhs_series_image",
                messages=[
                    {"role": "system", "content": IMAGE_GENERATE_SYSTEM},
                    {"role": "user", "content": full_prompt},
                ],
                visual_kind=vk,
                base_routing_hints=routing_hints,
            )
        except Exception as e:
            log.warning("batch_gen.xhs_chain_failed_fallback", idx=idx, err=str(e))
            resp = await llm.complete(
                task_type="image_generate",
                messages=[
                    {"role": "system", "content": IMAGE_GENERATE_SYSTEM},
                    {"role": "user", "content": full_prompt},
                ],
                routing_hints=routing_hints,
            )
    else:
        resp = await llm.complete(
            task_type="image_generate",
            messages=[
                {"role": "system", "content": IMAGE_GENERATE_SYSTEM},
                {"role": "user", "content": full_prompt},
            ],
            routing_hints=routing_hints,
        )
    ref, via = await _normalize_image_artifact(
        resp_content=resp.content if isinstance(resp.content, str) else "",
        task_id=task_id,
        step_id=f"{step_id}_{idx}",
    )
    return ref, via, resp.model, trail


async def batch_generate_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()
    image_specs: list[dict] = (
        task.parameters.get("image_specs")
        or task.inputs.get("image_specs")
        or []
    )
    base_prompt = task.inputs.get("_prompt") or task.inputs.get("prompt", "")
    count = int(task.parameters.get("count", len(image_specs) or 4))
    image_set_type = task.parameters.get("image_set_type", "default")
    style_hint = _SET_TYPE_STYLE_HINTS.get(image_set_type, _SET_TYPE_STYLE_HINTS["default"])

    # 若 image_specs 为空,用 base_prompt × count 扩展
    if not image_specs and base_prompt:
        image_specs = [{"prompt": base_prompt, "index": i} for i in range(count)]

    if not image_specs:
        return AgentResult(
            task_id=task.task_id,
            step_id=task.step_id,
            status="failed",
            error_detail={"reason": "no_image_specs_and_no_prompt"},
        )

    task_id = str(task.task_id)

    # Inject user style preferences from flywheel memory
    user_prefs = await get_user_prefs(str(task.user_id))
    pref_ctx = build_pref_context(user_prefs)
    style_base = f"[图集风格基调:{style_hint}]"
    md_k = ""
    if isinstance(task.inputs, dict):
        raw_md = task.inputs.get("_md_skill_knowledge")
        if isinstance(raw_md, str) and raw_md.strip():
            md_k = raw_md.strip()
    if md_k:
        style_base = f"{style_base}\n[小红书内容/卡片版式规范]\n{md_k}"
    if pref_ctx:
        style_base = f"{style_base}\n[用户偏好:{pref_ctx}]"

    # 第 1 张:风格锚点(串行,后续图的风格依赖锚点描述)
    anchor_ref, anchor_via, anchor_model, _anchor_trail = await _gen_one(
        spec=image_specs[0],
        idx=0,
        style_context=style_base,
        task_id=task_id,
        step_id=task.step_id,
        routing_hints=task.routing_hints,
    )

    # 风格一致性约束注入后续图 prompt
    style_context = (
        f"[风格一致性约束:{style_hint};"
        f"与图集第1张保持相同色调、构图、字体粗细]"
    )

    # 后续图并行生成
    rest_coros = [
        _gen_one(
            spec=spec,
            idx=i + 1,
            style_context=style_context,
            task_id=task_id,
            step_id=task.step_id,
            routing_hints=task.routing_hints,
        )
        for i, spec in enumerate(image_specs[1:])
    ]
    rest_results: list[tuple[str, str, str, list]] = (
        list(await asyncio.gather(*rest_coros)) if rest_coros else []
    )

    all_refs = [anchor_ref, *(r for r, _, _, _ in rest_results)]
    all_vias = [anchor_via, *(v for _, v, _, _ in rest_results)]

    # 写 manifest
    manifest = {
        "task_id": task_id,
        "step_id": task.step_id,
        "image_set_type": image_set_type,
        "count": len(all_refs),
        "image_refs": all_refs,
        "normalized_via": all_vias,
        "specs": [s.get("prompt", "")[:80] for s in image_specs],
    }
    manifest_ref = await put_json(
        key=f"artifacts/{task_id}/{task.step_id}/manifest.json",
        payload=manifest,
    )

    await emit(
        signal_type="trace",
        payload={
            "task_id": task_id,
            "step_id": task.step_id,
            "agent_id": "agent_3",
            "task_type": "batch_generate",
            "count": len(all_refs),
            "image_set_type": image_set_type,
            "model": anchor_model,
        },
    )

    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="completed",
        output=ArtifactRef(
            artifact_id=uuid4(),
            type="image_collection",
            reference=manifest_ref,
            extra_metadata={
                "count": len(all_refs),
                "image_refs": all_refs,
                "image_set_type": image_set_type,
                "model": anchor_model,
            },
        ),
        duration_ms=int((time.monotonic() - t0) * 1000),
        model_used=anchor_model,
    )
