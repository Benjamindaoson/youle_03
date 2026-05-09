"""Agent 1 version_compare — 生成 N 个差异化版本,JSON 输出。"""

from __future__ import annotations

import json
import time
from uuid import uuid4

from agents._common import llm
from agents._common.oss_writer import put_json
from agents._common.protocol import AgentResult, AgentTask, ArtifactRef

SYSTEM = """你是文案师,任务是为用户生成 N 个候选版本,让 ta 选一个。
输出严格 JSON 数组:[{"label":"版本A","content":"..."},{"label":"版本B","content":"..."}]
不要任何其他文字。"""


async def version_compare_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()
    prompt = task.inputs.get("_prompt") or task.inputs.get("prompt", "")
    n = int(task.parameters.get("count", 3))
    resp = await llm.complete(
        task_type="version_compare",
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"生成 {n} 个版本:{prompt}"},
        ],
        routing_hints=task.routing_hints,
        response_format={"type": "json_object"},
        temperature=0.9,
    )
    try:
        versions = json.loads(resp.content)
    except json.JSONDecodeError:
        versions = [{"label": "fallback", "content": resp.content}]

    oss_ref = await put_json(
        key=f"artifacts/{task.task_id}/{task.step_id}.json", payload={"versions": versions}
    )
    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="completed",
        output=ArtifactRef(
            artifact_id=uuid4(),
            type="structured",
            reference=oss_ref,
            extra_metadata={"version_count": len(versions)},
        ),
        cost_usd=resp.cost_usd,
        duration_ms=int((time.monotonic() - t0) * 1000),
        model_used=resp.model,
    )
