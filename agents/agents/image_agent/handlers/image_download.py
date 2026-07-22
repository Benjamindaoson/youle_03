"""Agent 3 image_download — 从研究结果下载图片并质检。"""

from __future__ import annotations

import asyncio
import io
import json
import os
import struct
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4
import zlib

import boto3
import structlog
from botocore.client import Config

from agents._common.flywheel_emitter import emit
from agents._common.mcp_client import mcp_client
from agents._common.oss_writer import put_bytes
from agents._common.protocol import AgentResult, AgentTask, ArtifactRef

log = structlog.get_logger(__name__)


def _s3():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("OSS_ENDPOINT", "http://localhost:9000"),
        aws_access_key_id=os.getenv("OSS_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.getenv("OSS_SECRET_KEY", "minioadmin"),
        config=Config(signature_version="s3v4"),
    )


def _read_oss_json(ref: str) -> dict[str, Any]:
    parsed = urlparse(ref)
    obj = _s3().get_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))
    return json.loads(obj["Body"].read().decode("utf-8"))


async def _urls_from_research_ref(ref: str | None) -> list[str]:
    if not ref or not ref.startswith("oss://"):
        return []

    def _load() -> list[str]:
        payload = _read_oss_json(ref)
        urls: list[str] = []
        for row in payload.get("results", []):
            if isinstance(row, dict):
                image_url = row.get("image_url") or row.get("图片URL")
                if image_url:
                    urls.append(str(image_url))
        return urls

    try:
        return await asyncio.to_thread(_load)
    except Exception as exc:
        log.warning("image_download.research_ref_read_failed", ref=ref, err=str(exc))
        return []


async def _cards_from_research_ref(task: AgentTask, ref: str | None, count: int = 5) -> list[str]:
    if not ref or not ref.startswith("oss://"):
        return []

    def _load_rows() -> list[dict[str, Any]]:
        payload = _read_oss_json(ref)
        rows = [row for row in payload.get("results", []) if isinstance(row, dict)]
        if not rows:
            rows = [
                {
                    "title": f"视频素材 {i + 1}",
                    "snippet": "围绕主题整理的背景资料与关键事实，可用于脚本和画面设计。",
                    "url": "https://example.com/",
                }
                for i in range(count)
            ]
        return rows[:count]

    try:
        rows = await asyncio.to_thread(_load_rows)
    except Exception as exc:
        log.warning("image_download.research_card_read_failed", ref=ref, err=str(exc))
        return []

    refs: list[str] = []
    for idx, row in enumerate(rows):
        data = _case_card_png(row, idx)
        refs.append(
            await put_bytes(
                key=f"artifacts/{task.task_id}/{task.step_id}/case-card-{idx + 1}.png",
                data=data,
                content_type="image/png",
            )
        )
    return refs


def _font(size: int) -> Any:
    try:
        from PIL import ImageFont

        candidates = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/System/Library/Fonts/PingFang.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
        for path in candidates:
            if Path(path).exists():
                return ImageFont.truetype(path, size)
        return ImageFont.load_default()
    except Exception:
        return None


def _wrap_text(text: str, max_chars: int) -> list[str]:
    text = " ".join(str(text).replace("\n", " ").split())
    if not text:
        return []
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def _case_card_png(row: dict[str, Any], idx: int) -> bytes:
    try:
        from PIL import Image, ImageDraw

        title = str(row.get("title") or row.get("标题") or f"视频素材 {idx + 1}")[:80]
        snippet = str(row.get("snippet") or row.get("摘要") or "围绕主题整理的背景资料与关键信息。")[:180]
        amount = str(row.get("涉案金额") or "")
        source = str(row.get("url") or row.get("来源URL") or "")

        bg = [(20, 31, 44), (48, 25, 52), (22, 45, 39), (55, 34, 28), (33, 38, 59)][idx % 5]
        accent = [(220, 38, 38), (234, 88, 12), (14, 165, 233), (22, 163, 74), (168, 85, 247)][idx % 5]
        img = Image.new("RGB", (1080, 1920), bg)
        draw = ImageDraw.Draw(img)

        draw.rectangle((0, 0, 1080, 220), fill=accent)
        draw.rectangle((80, 340, 1000, 1500), fill=(248, 250, 252))
        draw.rectangle((80, 1500, 1000, 1760), fill=(15, 23, 42))

        font_badge = _font(42)
        font_title = _font(58)
        font_body = _font(40)
        font_small = _font(30)
        draw.text((80, 72), "视频素材速览", font=font_badge, fill=(255, 255, 255))

        y = 410
        for line in _wrap_text(title, 14)[:4]:
            draw.text((130, y), line, font=font_title, fill=(15, 23, 42))
            y += 76

        y += 48
        if amount:
            draw.text((130, y), f"涉案金额: {amount}", font=font_body, fill=(185, 28, 28))
            y += 70
        for line in _wrap_text(snippet, 20)[:6]:
            draw.text((130, y), line, font=font_body, fill=(51, 65, 85))
            y += 58

        footer = "来源: " + (source[:45] if source else "公开报道")
        for line in _wrap_text(footer, 28)[:3]:
            draw.text((120, y + 60), line, font=font_small, fill=(226, 232, 240))
            y += 44

        draw.text((130, 1628), "城市漫游 · 发现日常灵感", font=font_body, fill=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:
        log.warning("image_download.case_card_pil_failed", err=str(exc))
        return _simple_png(
            1080,
            1920,
            bg=((18 + idx * 18) % 80, 30, 48),
            accent=(185, 28 + idx * 18 % 120, 28),
        )


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def _simple_png(width: int, height: int, *, bg: tuple[int, int, int], accent: tuple[int, int, int]) -> bytes:
    rows = []
    for y in range(height):
        if 120 <= y <= 300 or 1580 <= y <= 1760:
            color = accent
        elif 340 <= y <= 1500 and 80 <= width:
            color = (248, 250, 252)
        else:
            color = bg
        rows.append(b"\x00" + bytes(color) * width)
    raw = b"".join(rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, level=6))
        + _png_chunk(b"IEND", b"")
    )


async def image_download_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()
    urls = task.inputs.get("urls", []) or task.parameters.get("urls", [])
    if not urls:
        upstream = task.inputs.get("_upstream") or {}
        research_ref = upstream.get("research")
        urls = await _urls_from_research_ref(research_ref)
    else:
        research_ref = (task.inputs.get("_upstream") or {}).get("research")
    check_quality = bool(task.parameters.get("check_quality", True))
    min_resolution = task.parameters.get("min_resolution", "1080p")

    out = await mcp_client.call_tool(
        server="image_tools",
        tool="download_batch",
        arguments={
            "urls": urls,
            "check_quality": check_quality,
            "min_resolution": min_resolution,
        },
    )
    image_refs = out.get("image_refs", [])
    fallback_generated = False
    if len(image_refs) < 5:
        supplement = await _cards_from_research_ref(task, research_ref, count=5 - len(image_refs))
        image_refs = [*image_refs, *supplement]
        fallback_generated = bool(supplement)
        if fallback_generated:
            out["downloaded_count"] = len(image_refs)
            out["image_refs"] = image_refs
            out["oss_ref"] = f"oss://haole-dev/artifacts/{task.task_id}/{task.step_id}/"
    await emit(
        signal_type="trace",
        payload={
            "task_id": str(task.task_id),
            "step_id": task.step_id,
            "agent_id": "agent_3",
            "task_type": "image_download",
            "downloaded_count": out.get("downloaded_count", 0),
            "fallback_generated": fallback_generated,
            "image_ref_count": len(image_refs),
        },
    )

    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="completed",
        output=ArtifactRef(
            artifact_id=uuid4(),
            type="image_collection",
            reference=out.get(
                "oss_ref", f"oss://artifacts/{task.task_id}/{task.step_id}/"
            ),
            extra_metadata={
                "count": out.get("downloaded_count", 0),
                "rejected": out.get("rejected_count", 0),
                "image_refs": image_refs,
                "fallback_generated": fallback_generated,
            },
        ),
        duration_ms=int((time.monotonic() - t0) * 1000),
    )
