"""数据飞轮服务(ADR-011 4 类信号沉淀必做)。

任务完成路径必须 emit 4 类信号:
  1. 工作流完整轨迹 → Postgres workflow_traces(+ OSS;Qdrant V1.5)
  2. 用户偏好沉淀 → user_preferences.preferences(频次聚合,无向量)
  3. 失败 → Reflexion → prompt_improvement_candidates(异步 runner)
  4. 高满意度 → Skill 草稿 → skill_drafts(异步 runner)

Package G:1/2 同步直写 DB(无外部依赖),3/4 推 Redis Stream 由 runner 异步处理。
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_preference import UserPreference
from app.models.workflow_trace import WorkflowTrace

log = structlog.get_logger(__name__)


# ── Redis stream emit(异步信号)──
_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
_redis: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(_REDIS_URL, decode_responses=True)
    return _redis


async def _emit_stream(signal_type: str, payload: dict[str, Any]) -> None:
    try:
        redis = await _get_redis()
        await redis.xadd(
            "flywheel:signals",
            {"type": signal_type, "payload": json.dumps(payload, ensure_ascii=False, default=str)},
        )
    except Exception as e:
        log.warning("flywheel.emit_failed", signal_type=signal_type, err=str(e))


# ── 偏好聚合(同步:频次足以决定 auto_apply,不需要 runner)──
def _confidence(count: int) -> float:
    if count >= 3:
        return 1.0
    if count == 2:
        return 0.7
    if count == 1:
        return 0.3
    return 0.0


class FlywheelService:
    @staticmethod
    async def emit_trace(
        session: AsyncSession,
        *,
        task_id: UUID,
        user_id: UUID,
        skill_id: UUID | None,
        skill_version: str | None,
        duration_ms: int | None,
        cost_usd: Decimal | None,
        user_satisfaction: int | None = None,
        failure_reason: str | None = None,
        rollback_count: int = 0,
        trace_oss_ref: str | None = None,
        qdrant_point_id: str | None = None,
        full_trace: dict[str, Any] | None = None,
    ) -> None:
        """同步直写 workflow_traces;同时把完整 trace 推给 ingestion runner 落 OSS。"""
        trace = WorkflowTrace(
            task_id=task_id,
            user_id=user_id,
            skill_id=skill_id,
            skill_version=skill_version,
            duration_ms=duration_ms,
            cost_usd=cost_usd,
            user_satisfaction=user_satisfaction,
            failure_reason=failure_reason,
            rollback_count=rollback_count,
            trace_oss_ref=trace_oss_ref,
            qdrant_point_id=qdrant_point_id,
        )
        session.add(trace)
        await session.commit()
        log.info("flywheel.trace.written", task_id=str(task_id))

        # 推 Stream:由 ingestion runner 异步落 OSS
        await _emit_stream(
            "trace",
            {
                "task_id": str(task_id),
                "user_id": str(user_id),
                "skill_id": str(skill_id) if skill_id else None,
                "skill_version": skill_version,
                "duration_ms": duration_ms,
                "cost_usd": float(cost_usd) if cost_usd else None,
                "user_satisfaction": user_satisfaction,
                "failure_reason": failure_reason,
                "rollback_count": rollback_count,
                "trace": full_trace or {},
            },
        )

        # Reflexion(失败)
        if failure_reason:
            await _emit_stream(
                "reflexion",
                {
                    "task_id": str(task_id),
                    "prompt_name": skill_version or "unknown",
                    "failure_reason": failure_reason,
                    "trace_excerpt": json.dumps(full_trace or {}, ensure_ascii=False)[:2000],
                },
            )

        # Skill drafter(高满意度)
        if (user_satisfaction or 0) >= 4:
            await _emit_stream(
                "skill_drafter",
                {
                    "task_id": str(task_id),
                    "user_id": str(user_id),
                    "trace": full_trace or {},
                    "user_satisfaction": user_satisfaction,
                },
            )

    @staticmethod
    async def emit_preference_update(
        session: AsyncSession,
        *,
        user_id: UUID,
        fields: dict[str, Any],
    ) -> None:
        """同步聚合用户字段选择频次到 user_preferences.preferences。"""
        if not fields:
            return
        row = await session.get(UserPreference, user_id)
        prefs: dict[str, Any] = dict(row.preferences) if row and row.preferences else {}
        for field, value in fields.items():
            bucket = dict(prefs.get(field) or {})
            values: dict[str, int] = dict(bucket.get("values") or {})
            key = (
                value
                if isinstance(value, str)
                else json.dumps(value, ensure_ascii=False, sort_keys=True)
            )
            values[key] = int(values.get(key, 0)) + 1
            confidence = {k: _confidence(v) for k, v in values.items()}
            top = max(confidence.items(), key=lambda kv: kv[1])
            bucket = {
                "values": values,
                "confidence": confidence,
                "auto_apply": top[0] if top[1] >= 1.0 else None,
                "last_updated": datetime.now(UTC).isoformat(),
            }
            prefs[field] = bucket

        if row is None:
            stmt = (
                pg_insert(UserPreference)
                .values(user_id=user_id, preferences=prefs)
                .on_conflict_do_update(
                    index_elements=["user_id"],
                    set_={"preferences": prefs, "updated_at": datetime.now(UTC)},
                )
            )
            await session.execute(stmt)
        else:
            row.preferences = prefs
        await session.commit()
        log.info("flywheel.preference.aggregated", user_id=str(user_id), field_count=len(fields))

    @staticmethod
    async def emit_reflexion_candidate(
        *,
        task_id: UUID,
        prompt_name: str,
        failure_reason: str,
        trace_excerpt: str = "",
    ) -> None:
        await _emit_stream(
            "reflexion",
            {
                "task_id": str(task_id),
                "prompt_name": prompt_name,
                "failure_reason": failure_reason,
                "trace_excerpt": trace_excerpt[:2000],
            },
        )

    @staticmethod
    async def emit_skill_draft(
        *,
        user_id: UUID,
        task_id: UUID,
        trace: dict[str, Any],
        user_satisfaction: int = 5,
    ) -> None:
        await _emit_stream(
            "skill_drafter",
            {
                "task_id": str(task_id),
                "user_id": str(user_id),
                "trace": trace,
                "user_satisfaction": user_satisfaction,
            },
        )


flywheel = FlywheelService()


# ── 用户偏好实时套用 ──
def auto_apply_from_preferences(
    *, prefs: dict[str, Any], schema: list[dict[str, Any]]
) -> dict[str, Any]:
    """v4 #267-269:连续 3 次同选 → 自动套用,不再问。"""
    out: dict[str, Any] = {}
    for sch in schema:
        name = sch.get("name")
        if not name:
            continue
        bucket = (prefs or {}).get(name) or {}
        auto = bucket.get("auto_apply")
        if auto is not None:
            out[name] = auto
    return out
