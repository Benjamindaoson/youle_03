"""视频合成 Celery workflow(GPU/CPU worker 上跑)。

链路:
  1. 解析 AgentTask payload
  2. 读 script 文本(从 OSS reference)
  3. 调 mcp-audio-tools.tts 生成 voiceover
  4. 调 mcp-video-tools.compose 真合成 mp4
  5. AgentResult.completed XADD 回 agent_results:{task_id} 流
     ↑ 主编排的 ResultConsumer 监听这个流,自动推进 task

铁律 5:任何 handler > 60s 走 Celery,这就是那个长任务。
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import boto3
import httpx
import redis
import structlog
from botocore.client import Config
from celery import Celery

log = structlog.get_logger(__name__)

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/2")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "http://minio:9000")
OSS_BUCKET = os.getenv("OSS_BUCKET", "haole-dev")

MCP_AUDIO_URL = os.getenv("MCP_AUDIO_TOOLS_URL", "http://mcp-audio-tools:7004")
MCP_VIDEO_URL = os.getenv("MCP_VIDEO_TOOLS_URL", "http://mcp-video-tools:7003")

celery_app = Celery(
    "haole-av",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="video",
)


def _s3():
    return boto3.client(
        "s3",
        endpoint_url=OSS_ENDPOINT,
        aws_access_key_id=os.getenv("OSS_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.getenv("OSS_SECRET_KEY", "minioadmin"),
        config=Config(signature_version="s3v4"),
    )


def _read_oss(ref: str) -> bytes:
    if not ref.startswith("oss://"):
        return b""
    parsed = urlparse(ref)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    obj = _s3().get_object(Bucket=bucket, Key=key)
    return obj["Body"].read()


def _resolve_image_refs(images_input: Any) -> list[str]:
    """images 可能是 ArtifactRef 引用结构,也可能是 list[str]。"""
    if isinstance(images_input, dict):
        meta = images_input.get("metadata", {})
        if isinstance(meta, dict) and "image_refs" in meta:
            return list(meta["image_refs"])
        if "reference" in images_input:
            return [images_input["reference"]]
    if isinstance(images_input, list):
        return [str(x) for x in images_input]
    if isinstance(images_input, str):
        return [images_input]
    return []


def _push_agent_result(*, task_id: str, payload: dict[str, Any]) -> None:
    """把 AgentResult JSON XADD 到 agent_results:{task_id} 让 TaskRunner 推进。"""
    r = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        r.xadd(f"agent_results:{task_id}", {"data": json.dumps(payload, ensure_ascii=False)})
    finally:
        with contextlib.suppress(Exception):
            r.close()


@celery_app.task(name="video_compose_workflow", bind=True, time_limit=900)
def video_compose_workflow(self, task_payload_json: str) -> dict[str, Any]:
    """长任务 — 执行完写回 agent_results 流让主编排推进。"""
    t0 = time.monotonic()
    try:
        task = json.loads(task_payload_json)
    except Exception as e:
        log.exception("video_workflow.parse_failed", err=str(e))
        return {"error": "parse_failed"}

    task_id = task.get("task_id")
    step_id = task.get("step_id")
    inputs = task.get("inputs", {})
    parameters = task.get("parameters", {})

    log.info("video_workflow.start", task_id=task_id, step_id=step_id)

    try:
        # 1. 拿 script 文本(从 inputs["script"]["reference"] 读 OSS)
        script_input = inputs.get("script") or {}
        script_ref = (
            script_input.get("reference")
            if isinstance(script_input, dict)
            else None
        )
        script_text = ""
        if script_ref:
            try:
                script_text = _read_oss(script_ref).decode("utf-8", errors="replace")
            except Exception as e:
                log.warning("video_workflow.script_read_failed", err=str(e))

        # 2. 解析时长(从 inputs / parameters / collected_fields)
        duration_field = parameters.get("duration_field", "60s")
        duration = _parse_duration(inputs.get("duration_seconds") or duration_field)

        # 3. 解析图片
        image_refs = _resolve_image_refs(inputs.get("images") or inputs.get("image_process"))

        # 4. 解析 BGM
        bgm_input = inputs.get("bgm") or {}
        bgm_ref = bgm_input.get("reference") if isinstance(bgm_input, dict) else None

        # 5. 调 mcp-audio-tools.tts
        voice = parameters.get("voice", "female_warm")
        voice_ref = None
        if script_text:
            try:
                with httpx.Client(timeout=120.0) as client:
                    resp = client.post(
                        f"{MCP_AUDIO_URL}/tools/tts",
                        json={"arguments": {"text": script_text[:2000], "voice": voice}},
                    )
                    resp.raise_for_status()
                    tts_out = resp.json()
                    voice_ref = tts_out.get("oss_ref")
            except Exception as e:
                log.warning("video_workflow.tts_failed", err=str(e))

        # 6. 调 mcp-video-tools.compose
        try:
            with httpx.Client(timeout=900.0) as client:
                resp = client.post(
                    f"{MCP_VIDEO_URL}/tools/compose",
                    json={
                        "arguments": {
                            "voice_ref": voice_ref,
                            "bgm_ref": bgm_ref,
                            "image_refs": image_refs,
                            "duration": duration,
                            "subtitle": script_text[:200] if script_text else None,
                            "resolution": [1080, 1920],
                            "bgm_volume": 0.55,
                            "voice_volume": 1.0,
                        }
                    },
                )
                resp.raise_for_status()
                compose_out = resp.json()
        except Exception as e:
            log.exception("video_workflow.compose_failed", err=str(e))
            _push_agent_result(
                task_id=task_id,
                payload={
                    "task_id": task_id,
                    "step_id": step_id,
                    "status": "failed",
                    "error_detail": {"reason": "compose_failed", "msg": str(e)},
                    "duration_ms": int((time.monotonic() - t0) * 1000),
                },
            )
            return {"status": "failed", "error": str(e)}

        if compose_out.get("_failed"):
            _push_agent_result(
                task_id=task_id,
                payload={
                    "task_id": task_id,
                    "step_id": step_id,
                    "status": "failed",
                    "error_detail": {"reason": "compose_returned_error", "msg": compose_out.get("error")},
                    "duration_ms": int((time.monotonic() - t0) * 1000),
                },
            )
            return {"status": "failed", "error": compose_out.get("error")}

        # 7. AgentResult 写回 agent_results 流 → 触发 TaskRunner.handle_result
        result_payload = {
            "task_id": task_id,
            "step_id": step_id,
            "status": "completed",
            "output": {
                "artifact_id": str(uuid4()),
                "type": "video",
                "reference": compose_out["oss_ref"],
                "extra_metadata": {
                    "duration_seconds": compose_out.get("duration_seconds", duration),
                    "size_bytes": compose_out.get("size_bytes"),
                    "resolution": "1080x1920",
                    "voice_ref": voice_ref,
                    "bgm_ref": bgm_ref,
                    "image_count": len(image_refs),
                },
            },
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "model_used": "moviepy+ffmpeg",
        }
        _push_agent_result(task_id=task_id, payload=result_payload)

        log.info(
            "video_workflow.done",
            task_id=task_id,
            step_id=step_id,
            duration_ms=result_payload["duration_ms"],
        )
        return {"status": "completed", "oss_ref": compose_out["oss_ref"]}

    except Exception as e:
        log.exception("video_workflow.unexpected", err=str(e))
        _push_agent_result(
            task_id=task_id,
            payload={
                "task_id": task_id,
                "step_id": step_id,
                "status": "failed",
                "error_detail": {"reason": "unexpected", "msg": str(e)},
                "duration_ms": int((time.monotonic() - t0) * 1000),
            },
        )
        return {"status": "failed", "error": str(e)}


def _parse_duration(field: Any) -> int:
    if isinstance(field, int):
        return field
    s = str(field).strip().lower().rstrip("s")
    return int(s) if s.isdigit() else 60
