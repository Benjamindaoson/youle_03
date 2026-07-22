"""Agent 4 bgm_select — 从素材库取候选,由 LLM 选择合适 BGM。

兜底层次(铁律 12):
1. DB 候选 → LLM 选择
2. DB 候选 → 规则选择
3. 本地 MP3 文件(local_materials/music/)→ 上传 OSS 后引用
4. 占位 oss:// ref(不阻塞下游)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import boto3
import structlog
from botocore.client import Config
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agents._common import llm
from agents._common.flywheel_emitter import emit
from agents._common.prompts import BGM_SELECT_SYSTEM
from agents._common.oss_writer import put_bytes
from agents._common.protocol import AgentResult, AgentTask, ArtifactRef

log = structlog.get_logger(__name__)

# local_materials/music/ は agents パッケージから 3 层上
_MUSIC_DIR = Path(__file__).parent.parent.parent.parent / "local_materials" / "music"

_MOOD_TO_LOCAL_FILE: dict[str, str] = {
    "calm": "惬意bgm.mp3",
    "relaxed": "惬意bgm.mp3",
    "neutral": "惬意bgm.mp3",
    "cozy": "惬意bgm.mp3",
    "energetic": "激情bgm.mp3",
    "exciting": "激情bgm.mp3",
    "upbeat": "激情bgm.mp3",
    "intense": "激情bgm.mp3",
}


def _parse_duration(field: str | int) -> int:
    if isinstance(field, int):
        return field
    s = str(field).strip().lower().rstrip("s")
    return int(s) if s.isdigit() else 60


def _s3():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("OSS_ENDPOINT", "http://localhost:9000"),
        aws_access_key_id=os.getenv("OSS_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.getenv("OSS_SECRET_KEY", "minioadmin"),
        config=Config(signature_version="s3v4"),
    )


def _read_oss_text(ref: str | None) -> str:
    if not ref or not ref.startswith("oss://"):
        return ""
    parsed = urlparse(ref)
    obj = _s3().get_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))
    return obj["Body"].read().decode("utf-8", errors="replace")


def _choose_rule_based(candidates: list[dict[str, Any]], duration: int) -> dict[str, Any] | None:
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: (abs(int(item.get("duration") or duration) - duration), int(item.get("usage_count") or 0)),
    )[0]


async def _choose_with_llm(
    *,
    candidates: list[dict[str, Any]],
    script_text: str,
    mood: str,
    duration: int,
    routing_hints: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not candidates:
        return None
    try:
        resp = await llm.complete(
            task_type="bgm_select",
            routing_hints=routing_hints,
            temperature=0.2,
            max_tokens=300,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": BGM_SELECT_SYSTEM,
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "目标情绪": mood,
                            "视频时长秒": duration,
                            "脚本": script_text[:1200],
                            "候选BGM": candidates,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        picked = json.loads(resp.content)
        picked_id = str(picked.get("id") or "")
        for item in candidates:
            if str(item.get("id")) == picked_id:
                item["selection_reason"] = picked.get("reason")
                item["selected_by"] = resp.model
                return item
    except Exception as exc:
        log.warning("bgm_select.llm_failed", err=str(exc))
    return None


async def _local_mp3_fallback(mood: str, task_id: str, step_id: str) -> str | None:
    """本地 MP3 兜底:找到对应文件后上传 OSS,返回 oss:// ref;找不到返回 None。"""
    filename = _MOOD_TO_LOCAL_FILE.get(mood) or "惬意bgm.mp3"
    local_path = _MUSIC_DIR / filename
    if not local_path.exists():
        # 降序尝试另一个文件
        for candidate in _MOOD_TO_LOCAL_FILE.values():
            p = _MUSIC_DIR / candidate
            if p.exists():
                local_path = p
                filename = candidate
                break
        else:
            return None

    try:
        data = local_path.read_bytes()
        oss_key = f"bgm-local/{filename}"
        ref = await put_bytes(key=oss_key, data=data, content_type="audio/mpeg")
        log.info("bgm_select.local_fallback_used", file=filename, oss_ref=ref)
        return ref
    except Exception as e:
        log.warning("bgm_select.local_fallback_upload_failed", file=filename, err=str(e))
        return None


async def bgm_select_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()
    mood = task.parameters.get("mood", "neutral")
    duration_field = task.parameters.get("duration_field", "60s")
    if duration_field in task.inputs:
        duration_field = task.inputs[duration_field]
    duration = _parse_duration(duration_field)
    script_ref = (task.inputs.get("_upstream") or {}).get("script")
    script_text = _read_oss_text(script_ref)

    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://haole:haole_dev@postgres:5432/haole")
    engine = create_async_engine(db_url, pool_pre_ping=True)
    Session = async_sessionmaker(bind=engine, expire_on_commit=False)

    try:
        async with Session() as session:
            from sqlalchemy import text as sa_text

            rows = await session.execute(
                sa_text(
                    """
                    SELECT id::text, title, mood, oss_ref, duration, bpm, license, usage_count
                    FROM bgm_library
                    WHERE is_active = TRUE
                      AND ABS(duration - :dur) < 45
                    ORDER BY CASE WHEN mood = :mood THEN 0 ELSE 1 END,
                             ABS(duration - :dur), usage_count ASC
                    LIMIT 8
                    """
                ),
                {"mood": mood, "dur": duration},
            )
            candidates = [dict(row._mapping) for row in rows.fetchall()]
            if not candidates:
                rows = await session.execute(
                    sa_text(
                        """
                        SELECT id::text, title, mood, oss_ref, duration, bpm, license, usage_count
                        FROM bgm_library
                        WHERE is_active = TRUE
                        ORDER BY ABS(duration - :dur), usage_count ASC
                        LIMIT 8
                        """
                    ),
                    {"dur": duration},
                )
                candidates = [dict(row._mapping) for row in rows.fetchall()]
    finally:
        await engine.dispose()

    selected = await _choose_with_llm(
        candidates=candidates,
        script_text=script_text,
        mood=mood,
        duration=duration,
        routing_hints=task.routing_hints,
    ) or _choose_rule_based(candidates, duration)

    fallback_source = None
    if selected is None:
        # 层 3:本地 MP3 文件兜底
        local_ref = await _local_mp3_fallback(mood, str(task.task_id), task.step_id)
        if local_ref:
            oss_ref = local_ref
            meta = {"mood": mood, "duration": duration, "fallback": True, "fallback_source": "local_mp3"}
            fallback_source = "local_mp3"
        else:
            # 层 4:占位 ref(保证下游不崩)
            oss_ref = f"oss://bgm/placeholder_{mood}_{duration}s.mp3"
            meta = {"mood": mood, "duration": duration, "fallback": True, "fallback_source": "placeholder"}
            fallback_source = "placeholder"
    else:
        oss_ref = selected["oss_ref"]
        meta = {
            "mood": selected.get("mood") or mood,
            "duration": int(selected.get("duration") or duration),
            "title": selected.get("title"),
            "bgm_id": selected.get("id"),
            "selected_by": selected.get("selected_by", "rule_based"),
            "selection_reason": selected.get("selection_reason"),
            "candidate_count": len(candidates),
        }

    await emit(
        signal_type="trace",
        payload={
            "task_id": str(task.task_id),
            "step_id": task.step_id,
            "agent_id": "agent_4",
            "task_type": "bgm_select",
            "mood": mood,
            "candidate_count": len(candidates),
            "fallback_source": fallback_source,
        },
    )

    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="completed",
        output=ArtifactRef(
            artifact_id=uuid4(), type="audio", reference=oss_ref, extra_metadata=meta
        ),
        duration_ms=int((time.monotonic() - t0) * 1000),
    )
