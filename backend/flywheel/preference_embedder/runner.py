"""信号 2:用户偏好沉淀(v4 #267-273)。

简化方案(用户指定跳过 BGE+Qdrant):
- 不做向量;仅基于次数统计
- 同一字段连续 3 次同选 → confidence 1.0(自动套用)
- 1 次 = 0.3 / 2 次 = 0.7 / 3 次 = 1.0
- 偏好画像存 user_preferences.preferences JSONB:
    {
      "字段名": {
        "values": {"值A": 3, "值B": 1},
        "confidence": {"值A": 1.0, "值B": 0.3},
        "auto_apply": "值A",
        "last_updated": "2026-05-06T..."
      }
    }
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.models.user_preference import UserPreference

log = structlog.get_logger(__name__)


def _confidence(count: int) -> float:
    if count >= 3:
        return 1.0
    if count == 2:
        return 0.7
    if count == 1:
        return 0.3
    return 0.0


async def _aggregate(
    session: AsyncSession, *, user_id: UUID, field: str, value: Any
) -> None:
    """聚合一个字段值的频次。upsert 到 user_preferences.preferences。"""
    row = await session.get(UserPreference, user_id)
    prefs: dict[str, Any] = dict(row.preferences) if row and row.preferences else {}
    bucket = dict(prefs.get(field) or {})
    values: dict[str, int] = dict(bucket.get("values") or {})
    key = json.dumps(value, ensure_ascii=False, sort_keys=True) if not isinstance(value, str) else value
    values[key] = int(values.get(key, 0)) + 1
    confidence = {k: _confidence(v) for k, v in values.items()}
    auto = max(confidence.items(), key=lambda kv: kv[1])
    bucket = {
        "values": values,
        "confidence": confidence,
        "auto_apply": auto[0] if auto[1] >= 1.0 else None,
        "last_updated": datetime.now(UTC).isoformat(),
    }
    prefs[field] = bucket

    if row is None:
        # 用 INSERT ... ON CONFLICT 处理首次创建竞态
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


async def _process(payload: dict[str, Any]) -> None:
    user_id = payload.get("user_id")
    fields = payload.get("fields") or {}  # {字段名: 值}
    if not user_id or not isinstance(fields, dict):
        return
    async with SessionLocal() as session:
        uid = UUID(user_id)
        for field, value in fields.items():
            await _aggregate(session, user_id=uid, field=field, value=value)
        log.info(
            "flywheel.preference.aggregated",
            user_id=str(uid),
            field_count=len(fields),
        )


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
        except Exception as e:
            log.warning("flywheel.preference.xread_failed", err=str(e))
            await asyncio.sleep(2)
            continue
        if not resp:
            continue
        for _stream, messages in resp:
            for msg_id, fields in messages:
                last_id = msg_id
                if fields.get("type") != "preference":
                    continue
                try:
                    payload = json.loads(fields.get("payload", "{}"))
                except json.JSONDecodeError:
                    continue
                await _process(payload)


if __name__ == "__main__":
    asyncio.run(main())
