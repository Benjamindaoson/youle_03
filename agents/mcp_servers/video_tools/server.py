"""mcp-video-tools:compose(MoviePy 真合成)/ extract_frames / subtitle_align。

compose 的输入约定:
- voice_ref:  oss:// or http(s)://  voiceover mp3
- bgm_ref:    oss:// or http(s)://  background music mp3
- image_refs: list of oss/http URLs of jpg/png frames(按顺序展示)
- duration:   总时长(秒)
- subtitle:   可选的字幕文本(整段,按时长均匀分布;V1 简化)
- resolution: [w, h] tuple,默认 1080x1920(竖屏短视频)
- bgm_volume: 0..1 默认 0.2(voice 1.0 主轨)

输出:{"oss_ref": "oss://...mp4", "duration_seconds": 60, "size_bytes": 1234567}
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import boto3
import httpx
import structlog
from botocore.client import Config

from mcp_servers._shared.http_app import make_app

log = structlog.get_logger(__name__)

OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "http://minio:9000")
OSS_BUCKET = os.getenv("OSS_BUCKET", "haole-dev")


def _font(size: int):
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


def _wrap_text(text: str, max_chars: int) -> list[str]:
    cleaned = " ".join(str(text).replace("\n", " ").split())
    return [cleaned[i : i + max_chars] for i in range(0, len(cleaned), max_chars)]


def _subtitle_png(text: str, width: int) -> bytes:
    from PIL import Image, ImageDraw

    font = _font(46)
    lines = _wrap_text(text[:180], 18)[:4]
    line_h = 62
    pad_x = 44
    pad_y = 30
    box_w = width - 96
    box_h = pad_y * 2 + max(1, len(lines)) * line_h
    img = Image.new("RGBA", (box_w, box_h), (15, 23, 42, 210))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, box_w - 1, box_h - 1), radius=24, fill=(15, 23, 42, 220))
    y = pad_y
    for line in lines:
        draw.text((pad_x, y), line, font=font, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))
        y += line_h
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _s3():
    return boto3.client(
        "s3",
        endpoint_url=OSS_ENDPOINT,
        aws_access_key_id=os.getenv("OSS_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.getenv("OSS_SECRET_KEY", "minioadmin"),
        config=Config(signature_version="s3v4"),
    )


def _read_ref(ref: str) -> bytes:
    if ref.startswith("oss://"):
        parsed = urlparse(ref)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        obj = _s3().get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()
    if ref.startswith(("http://", "https://")):
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            return client.get(ref).content
    # 本地路径
    return Path(ref).read_bytes()


def _put_oss(key: str, data: bytes, content_type: str) -> str:
    _s3().put_object(Bucket=OSS_BUCKET, Key=key, Body=data, ContentType=content_type)
    return f"oss://{OSS_BUCKET}/{key}"


def _do_compose(
    *,
    voice_ref: str | None,
    bgm_ref: str | None,
    image_refs: list[str],
    duration: int,
    subtitle: str | None,
    resolution: tuple[int, int],
    bgm_volume: float,
    voice_volume: float,
) -> tuple[str, int, int]:
    """同步实现 — Celery worker / asyncio.to_thread 调用。返回 (oss_ref, duration, size_bytes)。"""
    from PIL import Image

    if not hasattr(Image, "ANTIALIAS"):
        Image.ANTIALIAS = Image.Resampling.LANCZOS  # type: ignore[attr-defined]

    # 延迟 import,避免在 server 启动期就要求 ffmpeg(测试便利)
    from moviepy.editor import (
        AudioFileClip,
        CompositeAudioClip,
        ImageClip,
        CompositeVideoClip,
        concatenate_videoclips,
    )

    if not image_refs:
        raise ValueError("compose: 至少需要 1 张图片")
    if duration <= 0:
        raise ValueError("compose: duration 必须 > 0")

    target_w, target_h = resolution

    with tempfile.TemporaryDirectory(prefix="haole-compose-") as workdir:
        wd = Path(workdir)

        # 1. 下载图片
        img_paths: list[Path] = []
        for i, ref in enumerate(image_refs):
            data = _read_ref(ref)
            p = wd / f"img_{i:03d}.jpg"
            p.write_bytes(data)
            img_paths.append(p)

        # 2. 创建 ImageClip 序列(等分时长)
        per_img = duration / len(img_paths)
        clips = []
        for p in img_paths:
            clip = (
                ImageClip(str(p))
                .set_duration(per_img)
                .resize(newsize=(target_w, target_h))  # 简化:直接缩放,V1.5 加智能裁切
            )
            clips.append(clip)
        video = concatenate_videoclips(clips, method="compose")

        # 3. 字幕(V1 简化:整段在底部,4/5 高度位置)
        if subtitle:
            try:
                subtitle_path = wd / "subtitle.png"
                subtitle_path.write_bytes(_subtitle_png(subtitle, target_w))
                txt = (
                    ImageClip(str(subtitle_path), transparent=True)
                    .set_duration(duration)
                    .set_position(("center", int(target_h * 0.76)))
                )
                video = CompositeVideoClip([video, txt])
            except Exception as e:
                log.warning("compose.subtitle_failed", err=str(e))

        # 4. 音频:voice + bgm 混音
        audio_tracks = []
        if voice_ref:
            voice_path = wd / "voice.mp3"
            voice_path.write_bytes(_read_ref(voice_ref))
            voice_clip = AudioFileClip(str(voice_path))
            if voice_clip.duration > duration:
                voice_clip = voice_clip.subclip(0, duration)
            voice_clip = voice_clip.volumex(voice_volume)
            audio_tracks.append(voice_clip)

        if bgm_ref:
            bgm_path = wd / "bgm.mp3"
            bgm_path.write_bytes(_read_ref(bgm_ref))
            bgm_clip = AudioFileClip(str(bgm_path))
            # 循环或裁剪到 duration
            if bgm_clip.duration < duration:
                from moviepy.editor import afx

                bgm_clip = bgm_clip.fx(afx.audio_loop, duration=duration)
            else:
                bgm_clip = bgm_clip.subclip(0, duration)
            bgm_clip = bgm_clip.volumex(bgm_volume)
            audio_tracks.append(bgm_clip)

        if audio_tracks:
            video = video.set_audio(CompositeAudioClip(audio_tracks))

        # 5. 导出
        out_path = wd / f"out_{uuid4().hex}.mp4"
        video.write_videofile(
            str(out_path),
            codec="libx264",
            audio_codec="aac",
            fps=24,
            preset="medium",
            threads=2,
            verbose=False,
            logger=None,
        )
        size_bytes = out_path.stat().st_size

        # 6. 上传 OSS
        oss_key = f"videos/{uuid4().hex}.mp4"
        data = out_path.read_bytes()
        oss_ref = _put_oss(oss_key, data, "video/mp4")

        # 释放
        with contextlib.suppress(Exception):
            video.close()

    return oss_ref, duration, size_bytes


async def compose(arguments: dict[str, Any]) -> dict[str, Any]:
    voice_ref = arguments.get("voice_ref")
    bgm_ref = arguments.get("bgm_ref")
    image_refs = arguments.get("image_refs") or arguments.get("images") or []
    duration = int(arguments.get("duration", 60))
    subtitle = arguments.get("subtitle")
    res = arguments.get("resolution", [1080, 1920])
    bgm_volume = float(arguments.get("bgm_volume", 0.2))
    voice_volume = float(arguments.get("voice_volume", 1.0))

    if not image_refs:
        return {"error": "compose: image_refs 必填", "_failed": True}

    try:
        oss_ref, dur, size = await asyncio.to_thread(
            _do_compose,
            voice_ref=voice_ref,
            bgm_ref=bgm_ref,
            image_refs=image_refs,
            duration=duration,
            subtitle=subtitle,
            resolution=(int(res[0]), int(res[1])),
            bgm_volume=bgm_volume,
            voice_volume=voice_volume,
        )
        return {"oss_ref": oss_ref, "duration_seconds": dur, "size_bytes": size}
    except Exception as e:
        log.exception("compose.failed", err=str(e))
        return {"error": str(e), "_failed": True}


async def extract_frames(arguments: dict[str, Any]) -> dict[str, Any]:
    """从视频提取关键帧。V1 简化为 mock; V1.5 接 FFmpeg。"""
    return {"frames": [], "_mock": True}


async def subtitle_align(arguments: dict[str, Any]) -> dict[str, Any]:
    """字幕对齐:把脚本切分到 voice mp3 的时间点。V1 简化为整段切分。"""
    text = arguments.get("text", "")
    duration = int(arguments.get("duration", 60))
    # V1 简化:按句号粗切,再把总时长均匀分到各段
    chunks = []
    if text:
        words = text.split("。")  # 按句号粗切
        words = [w.strip() for w in words if w.strip()]
        if words:
            per_chunk = duration / len(words)
            for i, w in enumerate(words):
                chunks.append(
                    {
                        "start": round(i * per_chunk, 2),
                        "end": round((i + 1) * per_chunk, 2),
                        "text": w,
                    }
                )
    return {"chunks": chunks, "_simplified": True}


app = make_app(
    server_name="video-tools",
    tools={"compose": compose, "extract_frames": extract_frames, "subtitle_align": subtitle_align},
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7003)
