"""Agent 2 local Pillow long-image composition for ecommerce delivery."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from mcp_servers.image_tools.server import concat_long_local

from agents._common.protocol import AgentResult, AgentTask, ArtifactRef


def _image_refs(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if not isinstance(value, dict):
        return []
    direct = value.get("image_refs")
    if isinstance(direct, list):
        return [str(item) for item in direct if item]
    metadata = value.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("image_refs"), list):
        return [str(item) for item in metadata["image_refs"] if item]
    return []


async def image_concat_long_handler(task: AgentTask) -> AgentResult:
    started = time.monotonic()
    images = _image_refs(task.inputs.get("images") or task.parameters.get("images", []))
    if not images:
        return AgentResult(
            task_id=task.task_id,
            step_id=task.step_id,
            status="failed",
            error_detail={"reason": "no_images"},
        )

    try:
        reference = await concat_long_local(
            images,
            direction=str(task.parameters.get("direction", "vertical")),
        )
    except Exception as exc:
        return AgentResult(
            task_id=task.task_id,
            step_id=task.step_id,
            status="failed",
            error_detail={"reason": "image_concat_failed", "message": str(exc)[:300]},
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="completed",
        output=ArtifactRef(
            artifact_id=uuid4(),
            type="image",
            reference=reference,
            extra_metadata={"input_count": len(images)},
        ),
        duration_ms=int((time.monotonic() - started) * 1000),
    )

