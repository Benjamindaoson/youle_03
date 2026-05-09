"""mcp-oss:upload / download / sign_url(后端 OSS 接口的 MCP 包装)。"""

from __future__ import annotations

import base64
import os
from typing import Any

import boto3
from botocore.client import Config

from mcp_servers._shared.http_app import make_app

OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "http://minio:9000")
OSS_ACCESS_KEY = os.getenv("OSS_ACCESS_KEY", "minioadmin")
OSS_SECRET_KEY = os.getenv("OSS_SECRET_KEY", "minioadmin")
OSS_BUCKET = os.getenv("OSS_BUCKET", "youle-dev")
OSS_REGION = os.getenv("OSS_REGION", "cn-hangzhou")

_s3: Any | None = None


def _client() -> Any:
    global _s3
    if _s3 is None:
        _s3 = boto3.client(
            "s3",
            endpoint_url=OSS_ENDPOINT,
            aws_access_key_id=OSS_ACCESS_KEY,
            aws_secret_access_key=OSS_SECRET_KEY,
            region_name=OSS_REGION,
            config=Config(signature_version="s3v4"),
        )
    return _s3


def _parse_ref(ref: str) -> tuple[str, str]:
    if not ref.startswith("oss://"):
        return OSS_BUCKET, ref.lstrip("/")
    rest = ref[len("oss://") :]
    bucket, _, key = rest.partition("/")
    return bucket or OSS_BUCKET, key


async def upload_bytes(arguments: dict[str, Any]) -> dict[str, Any]:
    object_key = arguments.get("object_key") or arguments.get("key") or "default.bin"
    bucket = arguments.get("bucket") or OSS_BUCKET
    content_type = arguments.get("content_type") or "application/octet-stream"
    if "body_base64" in arguments:
        body = base64.b64decode(arguments["body_base64"])
    else:
        body = str(arguments.get("body", "")).encode("utf-8")
    _client().put_object(Bucket=bucket, Key=object_key, Body=body, ContentType=content_type)
    return {"oss_ref": f"oss://{bucket}/{object_key}", "object_key": object_key, "ok": True}


async def download_bytes(arguments: dict[str, Any]) -> dict[str, Any]:
    ref = arguments.get("oss_ref") or arguments.get("object_key") or arguments.get("key")
    bucket, key = _parse_ref(str(ref or ""))
    obj = _client().get_object(Bucket=bucket, Key=key)
    body = obj["Body"].read()
    return {
        "oss_ref": f"oss://{bucket}/{key}",
        "object_key": key,
        "size": len(body),
        "body_base64": base64.b64encode(body).decode("ascii"),
        "content_type": obj.get("ContentType"),
    }


async def sign_url(arguments: dict[str, Any]) -> dict[str, Any]:
    ref = arguments.get("oss_ref") or arguments.get("object_key") or arguments.get("key")
    bucket, key = _parse_ref(str(ref or ""))
    expires_in = int(arguments.get("expires_in") or 3600)
    url = _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )
    return {
        "url": url,
        "oss_ref": f"oss://{bucket}/{key}",
        "expires_in": expires_in,
    }


app = make_app(
    server_name="oss",
    tools={
        "upload_bytes": upload_bytes,
        "download_bytes": download_bytes,
        "sign_url": sign_url,
    },
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7006)
