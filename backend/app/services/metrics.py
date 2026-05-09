"""轻量 Prometheus 指标生成器。

不引 prometheus_client(避免多 worker 文件锁问题),直接拼文本。
对接 Grafana 大盘的 4 个核心指标(对齐 Sprint 6 acceptance):
  1. youle_intent_latency_seconds        意图理解延迟
  2. youle_agent_queue_pending             Agent 队列积压
  3. youle_video_task_success_total        视频任务成功率
  4. youle_agent_status                    Agent 状态分布(0/1)

加 + 系统指标:
  - youle_tasks_total{status}              任务总数(running/completed/failed)
  - youle_hitl_open_total                   未关闭的 HITL gate 数
  - youle_dlq_total{agent}                 DLQ 积压
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta

import redis.asyncio as aioredis
import structlog
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.agent_status import AgentStatus
from app.models.hitl_gate import HITLGate
from app.models.task import Task

log = structlog.get_logger(__name__)

# 一些进程级累计计数(in-memory,简化)
_intent_latency_samples: list[float] = []
_intent_latency_lock_ts = 0.0


def record_intent_latency(seconds: float) -> None:
    """主编排意图理解模块在每次 dispatch 时调一次。"""
    global _intent_latency_lock_ts
    now = time.monotonic()
    # 滑动窗口:每次新增 trim 到最近 5 分钟样本
    _intent_latency_samples.append(seconds)
    if now - _intent_latency_lock_ts > 60:
        _intent_latency_lock_ts = now
        cutoff = len(_intent_latency_samples) - 1000
        if cutoff > 0:
            del _intent_latency_samples[:cutoff]


async def _redis() -> aioredis.Redis:
    return aioredis.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True
    )


def _percentile(samples: list[float], p: float) -> float:
    if not samples:
        return 0.0
    s = sorted(samples)
    idx = int(len(s) * p)
    idx = min(max(idx, 0), len(s) - 1)
    return s[idx]


async def render_prometheus_metrics() -> str:
    lines: list[str] = []
    p = lines.append

    # 1. 意图理解延迟
    if _intent_latency_samples:
        avg = sum(_intent_latency_samples) / len(_intent_latency_samples)
        p95 = _percentile(_intent_latency_samples, 0.95)
        p99 = _percentile(_intent_latency_samples, 0.99)
    else:
        avg = p95 = p99 = 0.0
    p("# HELP youle_intent_latency_seconds 意图理解模块延迟(秒)")
    p("# TYPE youle_intent_latency_seconds summary")
    p(f"youle_intent_latency_seconds_avg {avg:.4f}")
    p(f"youle_intent_latency_seconds{{quantile=\"0.95\"}} {p95:.4f}")
    p(f"youle_intent_latency_seconds{{quantile=\"0.99\"}} {p99:.4f}")
    p(f"youle_intent_latency_samples_total {len(_intent_latency_samples)}")

    # 2. Agent 队列积压(Redis Streams XLEN)
    try:
        r = await _redis()
        for kind in ("text", "document", "image", "av"):
            queue = f"agent_tasks:{kind}"
            pending = await r.xlen(queue)
            p("# HELP youle_agent_queue_pending Agent 队列积压数")
            p("# TYPE youle_agent_queue_pending gauge")
            p(f'youle_agent_queue_pending{{agent="{kind}"}} {pending}')
        # DLQ
        for kind in ("agent_1", "agent_2", "agent_3", "agent_4"):
            dlq = f"agent_dlq:{kind}"
            pending = await r.xlen(dlq)
            p(f'youle_dlq_total{{agent="{kind}"}} {pending}')
    except Exception as e:
        log.warning("metrics.redis_failed", err=str(e))

    # 3-4. DB 指标(任务状态 + HITL + Agent 状态分布)
    try:
        async with SessionLocal() as session:
            # 任务总数(过去 24h)
            cutoff = datetime.now(UTC) - timedelta(hours=24)
            rows = (
                await session.execute(
                    select(Task.status, func.count())
                    .where(Task.created_at >= cutoff)
                    .group_by(Task.status)
                )
            ).all()
            p("# HELP youle_tasks_total 24h 内任务数")
            p("# TYPE youle_tasks_total counter")
            for status, n in rows:
                p(f'youle_tasks_total{{status="{status}"}} {n}')

            # 视频任务成功率(从 skills 表 join domain=av)— 24h
            from app.models.skill import Skill

            video_rows = (
                await session.execute(
                    select(Task.status, func.count())
                    .join(Skill, Skill.id == Task.skill_id)
                    .where(Task.created_at >= cutoff, Skill.domain.in_(("av", "video")))
                    .group_by(Task.status)
                )
            ).all()
            video_done = sum(n for s, n in video_rows if s == "completed")
            video_fail = sum(n for s, n in video_rows if s == "failed")
            p(f"youle_video_task_success_total {video_done}")
            p(f"youle_video_task_failed_total {video_fail}")

            # HITL 未关闭门
            open_gates = await session.scalar(
                select(func.count(HITLGate.id)).where(HITLGate.closed_at.is_(None))
            )
            p(f"youle_hitl_open_total {open_gates or 0}")

            # Agent 状态分布
            status_rows = (
                await session.execute(
                    select(AgentStatus.agent_id, AgentStatus.status, func.count())
                    .group_by(AgentStatus.agent_id, AgentStatus.status)
                )
            ).all()
            p("# HELP youle_agent_status Agent 状态分布")
            p("# TYPE youle_agent_status gauge")
            for aid, status, n in status_rows:
                p(f'youle_agent_status{{agent="{aid}",status="{status}"}} {n}')
    except Exception as e:
        log.warning("metrics.db_failed", err=str(e))

    return "\n".join(lines) + "\n"
