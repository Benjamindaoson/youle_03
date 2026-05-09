"""Agent 端把产物写到 OSS(铁律 4:state 用引用)。

产物落 MinIO/OSS,只把 reference URL 返给主编排。
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import boto3
from botocore.client import Config

OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "http://minio:9000")
OSS_ACCESS_KEY = os.getenv("OSS_ACCESS_KEY", "minioadmin")
OSS_SECRET_KEY = os.getenv("OSS_SECRET_KEY", "minioadmin")
OSS_BUCKET = os.getenv("OSS_BUCKET", "youle-dev")

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


async def put_text(*, key: str, content: str, content_type: str = "text/plain") -> str:
    def _put() -> None:
        _client().put_object(
            Bucket=OSS_BUCKET, Key=key, Body=content.encode("utf-8"), ContentType=content_type
        )

    await asyncio.to_thread(_put)
    return f"oss://{OSS_BUCKET}/{key}"


async def put_bytes(*, key: str, data: bytes, content_type: str) -> str:
    def _put() -> None:
        _client().put_object(Bucket=OSS_BUCKET, Key=key, Body=data, ContentType=content_type)

    await asyncio.to_thread(_put)
    return f"oss://{OSS_BUCKET}/{key}"


async def put_json(*, key: str, payload: dict[str, Any]) -> str:
    import json

    return await put_text(
        key=key, content=json.dumps(payload, ensure_ascii=False), content_type="application/json"
    )
