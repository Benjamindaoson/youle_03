"""OSS 服务(dev: MinIO,prod: 阿里云 OSS)。

铁律:OSS 凭证不下发到客户端;前端只能拿预签名 URL。
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime
from typing import Any
from urllib.parse import quote

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.config import settings

_HEAD_OBJECT_MISSING_CODES = frozenset({"404", "403", "AccessDenied", "NoSuchKey", "NotFound"})
_HEAD_OBJECT_MISSING_STATUS_CODES = frozenset({403, 404})


class OSSService:
    def __init__(self) -> None:
        self._s3: Any | None = None

    def _client(self) -> Any:
        if self._s3 is None:
            self._s3 = boto3.client(
                "s3",
                endpoint_url=settings.OSS_ENDPOINT,
                aws_access_key_id=settings.OSS_ACCESS_KEY,
                aws_secret_access_key=settings.OSS_SECRET_KEY,
                region_name=settings.OSS_REGION,
                config=Config(signature_version="s3v4"),
                use_ssl=settings.OSS_USE_SSL,
            )
        return self._s3

    async def create_presigned_put(
        self, *, file_name: str, content_type: str, purpose: str
    ) -> tuple[str, str, int]:
        ts = datetime.utcnow().strftime("%Y%m%d")
        token = secrets.token_hex(8)
        object_key = f"{purpose}/{ts}/{token}_{file_name}"
        expires_in = 600

        def _generate() -> str:
            return self._client().generate_presigned_url(  # type: ignore[no-any-return]
                "put_object",
                Params={
                    "Bucket": settings.OSS_BUCKET,
                    "Key": object_key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in,
            )

        url = await asyncio.to_thread(_generate)
        return object_key, url, expires_in

    async def put_object(
        self, *, bucket: str | None, key: str, body: bytes, content_type: str
    ) -> str:
        target_bucket = bucket or settings.OSS_BUCKET

        def _put() -> None:
            self._client().put_object(
                Bucket=target_bucket, Key=key, Body=body, ContentType=content_type
            )

        await asyncio.to_thread(_put)
        return f"oss://{target_bucket}/{key}"

    @classmethod
    async def put(cls, *, bucket: str | None, key: str, body: bytes, content_type: str) -> str:
        """模块级简便接口(供 flywheel runners 用)。"""
        return await oss_service.put_object(bucket=bucket, key=key, body=body, content_type=content_type)

    async def get_object_url(self, object_key: str, expires_in: int = 3600) -> str:
        def _gen() -> str:
            return self._client().generate_presigned_url(  # type: ignore[no-any-return]
                "get_object",
                Params={"Bucket": settings.OSS_BUCKET, "Key": object_key},
                ExpiresIn=expires_in,
            )

        return await asyncio.to_thread(_gen)

    async def get_object_metadata(self, object_key: str) -> dict[str, object] | None:
        def _head() -> dict[str, object] | None:
            try:
                metadata = self._client().head_object(Bucket=settings.OSS_BUCKET, Key=object_key)
            except ClientError as exc:
                code = str(exc.response.get("Error", {}).get("Code", ""))
                status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                if code in _HEAD_OBJECT_MISSING_CODES or status_code in _HEAD_OBJECT_MISSING_STATUS_CODES:
                    return None
                raise
            return {
                "content_type": metadata.get("ContentType") or "",
                "size_bytes": metadata.get("ContentLength"),
            }

        return await asyncio.to_thread(_head)

    def build_public_url(self, object_key: str) -> str:
        endpoint = settings.OSS_ENDPOINT.rstrip("/")
        bucket = quote(settings.OSS_BUCKET.strip("/"), safe="")
        key = quote(object_key.lstrip("/"), safe="/")
        return f"{endpoint}/{bucket}/{key}"


oss_service = OSSService()
