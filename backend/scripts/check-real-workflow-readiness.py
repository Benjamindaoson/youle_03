"""Check whether local env is ready for a real short-video workflow run."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import boto3
import httpx
from botocore.client import Config
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(ROOT / ".env")
os.environ["DEBUG"] = "false"
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1,::1")

from app.db import SessionLocal, engine  # noqa: E402

REQUIRED_KEYS = [
    "OPENROUTER_API_KEY",
    "DEEPSEEK_API_KEY",
    "SILICONFLOW_API_KEY",
    "TAVILY_API_KEY",
]

MCP_HEALTH = {
    "search": os.getenv("MCP_SEARCH_URL", "http://localhost:7001"),
    "image_tools": os.getenv("MCP_IMAGE_TOOLS_URL", "http://localhost:7002"),
    "video_tools": os.getenv("MCP_VIDEO_TOOLS_URL", "http://localhost:7003"),
    "audio_tools": os.getenv("MCP_AUDIO_TOOLS_URL", "http://localhost:7004"),
    "document_tools": os.getenv("MCP_DOCUMENT_TOOLS_URL", "http://localhost:7005"),
    "oss": os.getenv("MCP_OSS_URL", "http://localhost:7006"),
}


def _has_real_key(name: str) -> bool:
    value = os.getenv(name, "").strip()
    return bool(value) and "mock" not in value.lower() and not value.endswith("...")


async def _check_mcp() -> list[tuple[str, bool, str]]:
    out = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, base in MCP_HEALTH.items():
            try:
                resp = await client.get(f"{base.rstrip('/')}/health")
                out.append((name, resp.status_code == 200, base))
            except Exception as exc:
                out.append((name, False, f"{base} ({exc})"))
    return out


def _check_minio() -> tuple[bool, str]:
    bucket = os.getenv("OSS_BUCKET", "youle-dev")
    client = boto3.client(
        "s3",
        endpoint_url=os.getenv("OSS_ENDPOINT", "http://localhost:9000"),
        aws_access_key_id=os.getenv("OSS_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.getenv("OSS_SECRET_KEY", "minioadmin"),
        region_name=os.getenv("OSS_REGION", "cn-hangzhou"),
        config=Config(signature_version="s3v4"),
    )
    try:
        client.head_bucket(Bucket=bucket)
    except Exception as exc:
        return False, f"{bucket} ({exc})"
    return True, bucket


async def _bgm_count() -> int:
    async with SessionLocal() as session:
        count = (
            await session.execute(
                text(
                    """
                    SELECT count(*)
                    FROM bgm_library
                    WHERE mood = 'warning'
                      AND is_active = TRUE
                      AND ABS(duration - 60) < 15
                    """
                )
            )
        ).scalar_one()
    return int(count)


async def main() -> None:
    failures = 0
    print("Real workflow readiness")

    litellm_mock = os.getenv("LITELLM_MOCK", "true").lower() == "true"
    print(f"[{'FAIL' if litellm_mock else ' OK '}] LITELLM_MOCK=false")
    failures += int(litellm_mock)

    for key in REQUIRED_KEYS:
        ok = _has_real_key(key)
        print(f"[{' OK ' if ok else 'FAIL'}] {key}")
        failures += int(not ok)

    ok, detail = _check_minio()
    print(f"[{' OK ' if ok else 'FAIL'}] MinIO/OSS bucket: {detail}")
    failures += int(not ok)

    for name, ok, detail in await _check_mcp():
        print(f"[{' OK ' if ok else 'FAIL'}] MCP {name}: {detail}")
        failures += int(not ok)

    bgm = await _bgm_count()
    print(f"[{' OK ' if bgm else 'FAIL'}] bgm_library warning ~60s rows: {bgm}")
    failures += int(not bgm)

    await engine.dispose()
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
