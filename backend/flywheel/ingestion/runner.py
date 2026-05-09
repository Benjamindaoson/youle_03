"""信号 1:工作流完整轨迹镜像。

简化方案(用户指定跳过 BGE-M3+Qdrant):
- 把 trace 完整 JSON 落 OSS(reference 写回 workflow_traces.trace_oss_ref)
- workflow_traces 行写入用于检索/统计的元数据(duration / cost / satisfaction)
- 不做向量索引,Qdrant 留作 V1.5 扩展点
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import redis.asyncio as aioredis
import structlog

from app.db import SessionLocal
from app.models.workflow_trace import WorkflowTrace

log = structlog.get_logger(__name__)

OSS_BUCKET = os.getenv("OSS_BUCKET", "youle-dev")


async def _write_oss(payload: dict[str, Any]) -> str:
    """把完整 trace 落 OSS;返回 oss:// 引用。

    V1 dev 用 minio,这里走轻量 boto3。失败时降级为本地伪引用。
    """
    task_id = payload.get("task_id") or "unknown"
    key = f"flywheel/traces/{datetime.now(UTC).strftime('%Y/%m/%d')}/{task_id}.json"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        # 复用 backend 已有的 OSS service
        from app.services.oss import OSSService

        await OSSService.put(bucket=OSS_BUCKET, key=key, body=body, content_type="application/json")
        return f"oss://{OSS_BUCKET}/{key}"
    except Exception as e:
        log.warning("flywheel.ingestion.oss_failed", err=str(e))
        return f"local://{key}"


async def _process(payload: dict[str, Any]) -> None:
    task_id = payload.get("task_id")
    if not task_id:
        return
    oss_ref = await _write_oss(payload)
    async with SessionLocal() as session:
        existing = (
            await session.execute(
                __import__("sqlalchemy").select(WorkflowTrace).where(
                    WorkflowTrace.task_id == UUID(task_id)
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.trace_oss_ref = oss_ref
            existing.duration_ms = payload.get("duration_ms") or existing.duration_ms
            existing.user_satisfaction = (
                payload.get("user_satisfaction") or existing.user_satisfaction
            )
        else:
            trace = WorkflowTrace(
                id=uuid4(),
                task_id=UUID(task_id),
                user_id=UUID(payload["user_id"]) if payload.get("user_id") else None,
                skill_id=UUID(payload["skill_id"]) if payload.get("skill_id") else None,
                skill_version=payload.get("skill_version"),
                duration_ms=payload.get("duration_ms"),
                cost_usd=Decimal(str(payload["cost_usd"])) if payload.get("cost_usd") else None,
                user_satisfaction=payload.get("user_satisfaction"),
                failure_reason=payload.get("failure_reason"),
                trace_oss_ref=oss_ref,
                rollback_count=payload.get("rollback_count", 0) or 0,
            )
            session.add(trace)
        await session.commit()
        log.info("flywheel.ingestion.written", task_id=task_id, oss_ref=oss_ref)


async def main() -> None:
    redis = aioredis.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True
    )
    last_id = "$"
    while True:
        try:
            resp = await redis.xread(
                {"flywheel:signals": last_id}, block=5000, count=10
            )
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.warning("flywheel.ingestion.xread_failed", err=str(e))
            await asyncio.sleep(2)
            continue
        if not resp:
            continue
        for _stream, messages in resp:
            for msg_id, fields in messages:
                last_id = msg_id
                if fields.get("type") != "trace":
                    continue
                try:
                    payload = json.loads(fields.get("payload", "{}"))
                except json.JSONDecodeError:
                    continue
                await _process(payload)


if __name__ == "__main__":
    asyncio.run(main())
