"""Agent 2 image_concat_long — 电商详情图最后一步:走 mcp-image-tools.concat_long。"""

from __future__ import annotations

import time
from uuid import uuid4

from agents._common.mcp_client import mcp_client
from agents._common.protocol import AgentResult, AgentTask, ArtifactRef


async def image_concat_long_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()
    images = task.inputs.get("images") or task.parameters.get("images", [])
    if isinstance(images, dict):
        images = images.get("image_refs", [])

    if not images:
        return AgentResult(
            task_id=task.task_id,
            step_id=task.step_id,
            status="failed",
            error_detail={"reason": "no_images"},
        )

    out = await mcp_client.call_tool(
        server="image_tools",
        tool="concat_long",
        arguments={
            "images": images,
            "direction": task.parameters.get("direction", "vertical"),
        },
    )

    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="completed",
        output=ArtifactRef(
            artifact_id=uuid4(),
            type="image",
            reference=out.get(
                "oss_ref", f"oss://artifacts/{task.task_id}/{task.step_id}.png"
            ),
            extra_metadata={"input_count": len(images)},
        ),
        duration_ms=int((time.monotonic() - t0) * 1000),
    )
