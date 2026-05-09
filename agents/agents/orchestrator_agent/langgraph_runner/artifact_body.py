"""从 OSS 拉回产物正文,供编排层 Jinja 注入(解决「只知 ref 不见内容」)。

大文件硬截断,避免 checkpoint 暴涨;默认总预算由环境变量控制。
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from urllib.parse import urlparse

import boto3
import structlog
from botocore.client import Config

log = structlog.get_logger(__name__)

OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "http://localhost:9000")
OSS_ACCESS_KEY = os.getenv("OSS_ACCESS_KEY", "minioadmin")
OSS_SECRET_KEY = os.getenv("OSS_SECRET_KEY", "minioadmin")
OSS_BUCKET = os.getenv("OSS_BUCKET", "youle-dev")

ORCH_HYDRATE_MAX_BYTES = int(os.getenv("ORCH_HYDRATE_MAX_BYTES", str(384 * 1024)))
ORCH_HYDRATE_ENABLED = os.getenv("ORCH_HYDRATE_ENABLED", "true").lower() in {"1", "true", "yes"}

_s3: Any | None = None


def _client() -> Any:
    global _s3
    if _s3 is None:
        _s3 = boto3.client(
            "s3",
            endpoint_url=OSS_ENDPOINT,
            aws_access_key_id=OSS_ACCESS_KEY,
            aws_secret_access_key=OSS_SECRET_KEY,
            region_name="cn-hangzhou",
            config=Config(signature_version="s3v4"),
        )
    return _s3


def _parse_oss_ref(ref: str) -> tuple[str, str] | None:
    if not ref.startswith("oss://"):
        return None
    p = urlparse(ref)
    bucket = p.netloc or OSS_BUCKET
    key = p.path.lstrip("/")
    if not key:
        return None
    return bucket, key


async def fetch_artifact_bytes(*, reference: str) -> bytes:
    """下载 oss:// 引用;非 oss 或失败返回 b\"\"。"""

    def _get() -> bytes:
        loc = _parse_oss_ref(reference)
        if not loc:
            return b""
        bucket, key = loc
        try:
            obj = _client().get_object(Bucket=bucket, Key=key)
            return obj["Body"].read()
        except Exception as e:
            log.warning("orch.hydrate.fetch_failed", ref=reference[:120], err=str(e))
            return b""

    return await asyncio.to_thread(_get)


async def fetch_artifact_text_excerpt(
    *,
    reference: str,
    artifact_type: str | None,
    max_bytes: int | None = None,
) -> dict[str, Any]:
    """返回可注入模板的片段: text / json / skipped。"""
    if not ORCH_HYDRATE_ENABLED or not reference.startswith("oss://"):
        return {"kind": "skipped", "text": "", "object": None, "truncated": False}

    cap = min(max_bytes or ORCH_HYDRATE_MAX_BYTES, ORCH_HYDRATE_MAX_BYTES)
    raw = await fetch_artifact_bytes(reference=reference)
    if not raw:
        return {"kind": "empty", "text": "", "object": None, "truncated": False}

    truncated = len(raw) > cap
    chunk = raw[:cap]

    at = (artifact_type or "").lower()
    if at in {"json", "structured", "quality_report"} or reference.endswith(".json"):
        try:
            obj = json.loads(chunk.decode("utf-8", errors="replace"))
            return {
                "kind": "json",
                "text": json.dumps(obj, ensure_ascii=False, indent=2) if isinstance(obj, (dict, list)) else str(obj),
                "object": obj if isinstance(obj, (dict, list)) else None,
                "truncated": truncated,
            }
        except Exception:
            pass

    text = chunk.decode("utf-8", errors="replace")
    return {"kind": "text", "text": text, "object": None, "truncated": truncated}
