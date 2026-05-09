"""Agent 4 video_compose handler — 长任务委托 Celery(铁律 5)。

行为:
- 立即派 Celery 任务,返回 status=pending_external + external_workflow_id
- TaskRunner 看到 pending_external → 不推进,等待 Celery 完成后写回 agent_results
- Celery worker 完成后由 video_workflow.video_compose_workflow 直接 XADD 到 agent_results 流
"""

from __future__ import annotations

import time

import structlog

from agents._common.protocol import AgentResult, AgentTask
from agents.av_agent.celery_tasks.video_workflow import video_compose_workflow

log = structlog.get_logger(__name__)


async def video_compose_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()
    # 估算时长(用于前端进度显示)
    duration_field = task.parameters.get("duration_field", "60s")
    estimated_seconds = _parse_duration(duration_field) * 6  # 经验值:每秒视频 ~6s 渲染

    # Celery 派活 — 不阻塞,workflow 完成后会自己 XADD agent_results:{task_id}
    workflow = video_compose_workflow.delay(task.model_dump_json())
    log.info(
        "video_compose.dispatched_celery",
        task_id=str(task.task_id),
        celery_id=workflow.id,
        estimated_render_s=estimated_seconds,
    )

    # 立即返 pending_external — TaskRunner 看到此 status 不推进,等真实 result
    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="pending_external",
        external_workflow_id=workflow.id,
        duration_ms=int((time.monotonic() - t0) * 1000),
    )


def _parse_duration(field):
    if isinstance(field, int):
        return field
    s = str(field).strip().lower().rstrip("s")
    return int(s) if s.isdigit() else 60
