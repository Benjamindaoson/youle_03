"""Agent 3 batch image generation handler."""

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
    "ecommerce": "clean ecommerce product composition, readable Chinese copy, consistent palette",
    "default": "consistent palette and composition across the complete image set",
}


async def _gen_one(
    *,
    spec: dict[str, Any],
    idx: int,
    style_context: str,
    task_id: str,
    step_id: str,
    routing_hints: dict[str, Any] | None,
    reference_images: list[str] | None = None,
) -> tuple[str, str, str, list[dict[str, Any]]]:
    """Generate one image and return its normalized artifact reference."""
    prompt = str(spec.get("prompt") or "")
    full_prompt = f"{style_context}\n{prompt}" if style_context else prompt
    trail: list[dict[str, Any]] = []

    if (routing_hints or {}).get("provider") == "ark_seedream":
        from agents.image_agent.handlers.ark_seedream import generate_seedream_image

        seedream = await generate_seedream_image(
            prompt=full_prompt,
            size=str(spec.get("size") or "2K"),
            reference_images=reference_images,
        )
        ref, via = await _normalize_image_artifact(
            resp_content=seedream.url,
            task_id=task_id,
            step_id=f"{step_id}_{idx}",
        )
        return ref, via, seedream.model, trail

    visual_kind = spec.get("xhs_visual_kind")
    if isinstance(visual_kind, str) and visual_kind:
        from agents.image_agent.xhs_image_router import generate_with_xhs_model_chain

        try:
            response, trail = await generate_with_xhs_model_chain(
                logical_task_type="xhs_series_image",
                messages=[
                    {"role": "system", "content": IMAGE_GENERATE_SYSTEM},
                    {"role": "user", "content": full_prompt},
                ],
                visual_kind=visual_kind,
                base_routing_hints=routing_hints,
            )
        except Exception:
            # Legacy non-ecommerce callers retain their existing generic path.
            response = await llm.complete(
                task_type="image_generate",
                messages=[
                    {"role": "system", "content": IMAGE_GENERATE_SYSTEM},
                    {"role": "user", "content": full_prompt},
                ],
                routing_hints=routing_hints,
            )
    else:
        response = await llm.complete(
            task_type="image_generate",
            messages=[
                {"role": "system", "content": IMAGE_GENERATE_SYSTEM},
                {"role": "user", "content": full_prompt},
            ],
            routing_hints=routing_hints,
        )

    ref, via = await _normalize_image_artifact(
        resp_content=response.content if isinstance(response.content, str) else "",
        task_id=task_id,
        step_id=f"{step_id}_{idx}",
    )
    return ref, via, response.model, trail


async def batch_generate_handler(task: AgentTask) -> AgentResult:
    """Generate a confirmed image collection and persist its manifest."""
    started = time.monotonic()
    image_specs: list[dict[str, Any]] = (
        task.parameters.get("image_specs") or task.inputs.get("image_specs") or []
    )
    base_prompt = task.inputs.get("_prompt") or task.inputs.get("prompt", "")
    count = int(task.parameters.get("count", len(image_specs) or 4))
    image_set_type = str(task.parameters.get("image_set_type", "default"))
    style_hint = _SET_TYPE_STYLE_HINTS.get(image_set_type, _SET_TYPE_STYLE_HINTS["default"])

    if not image_specs and base_prompt:
        image_specs = [{"prompt": base_prompt, "index": index} for index in range(count)]
    if not image_specs:
        return AgentResult(
            task_id=task.task_id,
            step_id=task.step_id,
            status="failed",
            error_detail={"reason": "no_image_specs_and_no_prompt"},
        )

    task_id = str(task.task_id)
    reference_images = task.inputs.get("reference_images") or []
    if not isinstance(reference_images, list):
        reference_images = [str(reference_images)]

    user_prefs = await get_user_prefs(str(task.user_id))
    preference_context = build_pref_context(user_prefs)
    style_base = f"[image set style: {style_hint}]"
    if preference_context:
        style_base = f"{style_base}\n[user preferences: {preference_context}]"

    try:
        anchor_ref, anchor_via, anchor_model, _ = await _gen_one(
            spec=image_specs[0],
            idx=0,
            style_context=style_base,
            task_id=task_id,
            step_id=task.step_id,
            routing_hints=task.routing_hints,
            reference_images=reference_images,
        )
        followup_context = (
            f"[style consistency: {style_hint}; "
            "keep the same palette, composition, and typography as image 1]"
        )
        rest = await asyncio.gather(
            *[
                _gen_one(
                    spec=spec,
                    idx=index + 1,
                    style_context=followup_context,
                    task_id=task_id,
                    step_id=task.step_id,
                    routing_hints=task.routing_hints,
                    reference_images=reference_images,
                )
                for index, spec in enumerate(image_specs[1:])
            ]
        )
    except Exception as exc:
        if (task.routing_hints or {}).get("provider") == "ark_seedream":
            return AgentResult(
                task_id=task.task_id,
                step_id=task.step_id,
                status="failed",
                error_detail={"reason": "ark_seedream_failed", "message": str(exc)[:300]},
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        raise

    all_refs = [anchor_ref, *(ref for ref, _, _, _ in rest)]
    all_vias = [anchor_via, *(via for _, via, _, _ in rest)]
    manifest = {
        "task_id": task_id,
        "step_id": task.step_id,
        "image_set_type": image_set_type,
        "count": len(all_refs),
        "image_refs": all_refs,
        "normalized_via": all_vias,
        "specs": [str(spec.get("prompt") or "")[:80] for spec in image_specs],
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
        duration_ms=int((time.monotonic() - started) * 1000),
        model_used=anchor_model,
    )

