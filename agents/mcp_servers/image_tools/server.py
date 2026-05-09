"""mcp-image-tools:bg_remove / enhance / concat_long(PIL 真实拼接)/ quality_check / download_batch。"""

from __future__ import annotations

import asyncio
import io
import os
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import boto3
import httpx
import structlog
from botocore.client import Config
from PIL import Image

from mcp_servers._shared.http_app import make_app

log = structlog.get_logger(__name__)

OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "http://minio:9000")
OSS_BUCKET = os.getenv("OSS_BUCKET", "youle-dev")


def _s3():
    return boto3.client(
        "s3",
        endpoint_url=OSS_ENDPOINT,
        aws_access_key_id=os.getenv("OSS_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.getenv("OSS_SECRET_KEY", "minioadmin"),
        config=Config(signature_version="s3v4"),
    )


def _read_oss(ref: str) -> bytes:
    """oss://bucket/key → bytes。"""
    if ref.startswith("oss://"):
        parsed = urlparse(ref)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
    else:
        bucket = OSS_BUCKET
        key = ref
    obj = _s3().get_object(Bucket=bucket, Key=key)
    return obj["Body"].read()


def _put_oss(key: str, data: bytes, content_type: str) -> str:
    _s3().put_object(Bucket=OSS_BUCKET, Key=key, Body=data, ContentType=content_type)
    return f"oss://{OSS_BUCKET}/{key}"


async def concat_long(arguments: dict[str, Any]) -> dict[str, Any]:
    """真实长图拼接:PIL 垂直拼接,等宽对齐。"""
    images = arguments.get("images", [])
    direction = arguments.get("direction", "vertical")
    if not images:
        return {"error": "no_images"}

    def _do() -> str:
        loaded: list[Image.Image] = []
        for ref in images:
            try:
                if str(ref).startswith("oss://"):
                    data = _read_oss(ref)
                elif str(ref).startswith(("http://", "https://")):
                    data = httpx.get(str(ref), timeout=20.0).content
                else:
                    data = _read_oss(ref)
                img = Image.open(io.BytesIO(data)).convert("RGB")
                loaded.append(img)
            except Exception as e:
                log.warning("concat.skip", ref=str(ref), err=str(e))

        if not loaded:
            raise RuntimeError("no images loaded")

        if direction == "vertical":
            target_w = max(img.width for img in loaded)
            resized = [
                (img if img.width == target_w else img.resize(
                    (target_w, int(img.height * target_w / img.width))
                ))
                for img in loaded
            ]
            total_h = sum(img.height for img in resized)
            canvas = Image.new("RGB", (target_w, total_h), (255, 255, 255))
            y = 0
            for img in resized:
                canvas.paste(img, (0, y))
                y += img.height
        else:
            target_h = max(img.height for img in loaded)
            resized = [
                (img if img.height == target_h else img.resize(
                    (int(img.width * target_h / img.height), target_h)
                ))
                for img in loaded
            ]
            total_w = sum(img.width for img in resized)
            canvas = Image.new("RGB", (total_w, target_h), (255, 255, 255))
            x = 0
            for img in resized:
                canvas.paste(img, (x, 0))
                x += img.width

        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        buf.seek(0)
        key = f"long-concat/{uuid4().hex}.png"
        return _put_oss(key, buf.getvalue(), "image/png")

    try:
        oss_ref = await asyncio.to_thread(_do)
        return {"oss_ref": oss_ref, "count": len(images)}
    except Exception as e:
        log.warning("concat.failed", err=str(e))
        return {"error": str(e), "_mock": True, "oss_ref": f"oss://{OSS_BUCKET}/mock-concat.png"}


async def download_batch(arguments: dict[str, Any]) -> dict[str, Any]:
    """从 URL 列表下载图片 → 落 OSS,可选质检过滤。"""
    urls = arguments.get("urls", [])
    check_quality = bool(arguments.get("check_quality", False))
    min_width = 1080 if arguments.get("min_resolution") == "1080p" else 720

    saved: list[str] = []
    rejected = 0

    async def _fetch(u: str) -> bytes | None:
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(u, headers={"User-Agent": "youle/1.0"})
                if resp.status_code == 200:
                    return resp.content
        except Exception as e:
            log.warning("download.failed", url=u, err=str(e))
        return None

    for u in urls:
        data = await _fetch(str(u))
        if data is None:
            rejected += 1
            continue
        try:
            img = Image.open(io.BytesIO(data))
            if check_quality and img.width < min_width:
                rejected += 1
                continue
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=85)
            buf.seek(0)
            key = f"downloads/{uuid4().hex}.jpg"
            saved.append(await asyncio.to_thread(_put_oss, key, buf.getvalue(), "image/jpeg"))
        except Exception:
            rejected += 1

    return {
        "downloaded_count": len(saved),
        "rejected_count": rejected,
        "image_refs": saved,
        "oss_ref": f"oss://{OSS_BUCKET}/downloads/manifest-{uuid4().hex}/",
    }


def _do_bg_remove(ref: str) -> tuple[str, bool]:
    """优先 rembg(深度模型),没装时退回 PIL 简易抠图(白底/纯色背景检测)。"""
    data = _read_oss(ref) if str(ref).startswith("oss://") else httpx.get(str(ref), timeout=20.0).content
    try:
        from rembg import remove

        out = remove(data)  # PNG with alpha
        used_real = True
    except ImportError:
        # 退化:把近白(>240)/近黑(<15)替换为透明
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        pixels = img.load()
        for y in range(img.height):
            for x in range(img.width):
                r, g, b, _ = pixels[x, y]
                if (r > 240 and g > 240 and b > 240) or (r < 15 and g < 15 and b < 15):
                    pixels[x, y] = (255, 255, 255, 0)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        out = buf.getvalue()
        used_real = False
    key = f"bg-removed/{uuid4().hex}.png"
    return _put_oss(key, out, "image/png"), used_real


async def bg_remove(arguments: dict[str, Any]) -> dict[str, Any]:
    """V1.5 接 rembg / Photoroom;V1 PIL fallback 也能跑。"""
    ref = arguments.get("ref") or arguments.get("oss_ref") or arguments.get("url")
    if not ref:
        return {"error": "ref 必填", "_failed": True}
    try:
        oss_ref, used_real = await asyncio.to_thread(_do_bg_remove, str(ref))
        return {"oss_ref": oss_ref, "engine": "rembg" if used_real else "pil_fallback"}
    except Exception as e:
        log.warning("bg_remove.failed", err=str(e))
        return {"oss_ref": f"oss://{OSS_BUCKET}/bg-removed-mock.png", "_mock": True, "error": str(e)}


def _do_enhance(ref: str, scale: int) -> tuple[str, dict[str, int]]:
    """优先 Real-ESRGAN(若装了),否则 PIL LANCZOS 上采样 + 锐化(简易增强)。"""
    data = _read_oss(ref) if str(ref).startswith("oss://") else httpx.get(str(ref), timeout=20.0).content
    img = Image.open(io.BytesIO(data)).convert("RGB")
    target = (img.width * scale, img.height * scale)
    try:
        # Real-ESRGAN 接入预留(V1.5):
        # from realesrgan import RealESRGANer; out_img = ...
        raise ImportError("realesrgan not configured")
    except ImportError:
        from PIL import ImageFilter

        out_img = img.resize(target, Image.LANCZOS).filter(ImageFilter.SHARPEN)

    buf = io.BytesIO()
    out_img.save(buf, format="JPEG", quality=92)
    key = f"enhanced/{uuid4().hex}.jpg"
    return (
        _put_oss(key, buf.getvalue(), "image/jpeg"),
        {"width": out_img.width, "height": out_img.height},
    )


async def enhance(arguments: dict[str, Any]) -> dict[str, Any]:
    ref = arguments.get("ref") or arguments.get("oss_ref") or arguments.get("url")
    scale = int(arguments.get("scale", 2))
    if not ref:
        return {"error": "ref 必填", "_failed": True}
    if scale not in (2, 3, 4):
        scale = 2
    try:
        oss_ref, dims = await asyncio.to_thread(_do_enhance, str(ref), scale)
        return {"oss_ref": oss_ref, "scale": scale, **dims}
    except Exception as e:
        log.warning("enhance.failed", err=str(e))
        return {"oss_ref": f"oss://{OSS_BUCKET}/enhanced-mock.jpg", "_mock": True, "error": str(e)}


def _do_quality_check(ref: str, min_width: int) -> dict[str, Any]:
    """简易客观质检:分辨率/对比度/锐度;V1.5 可接 LLM 评估美学。"""
    data = _read_oss(ref) if str(ref).startswith("oss://") else httpx.get(str(ref), timeout=20.0).content
    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size

    # 简易锐度(拉普拉斯近似):用 ImageStat 算亮度方差
    from PIL import ImageStat

    grayscale = img.convert("L")
    stat = ImageStat.Stat(grayscale)
    variance = stat.var[0] if stat.var else 0.0  # 越大越锐
    mean = stat.mean[0]

    issues: list[str] = []
    if w < min_width:
        issues.append(f"分辨率不足({w}<{min_width})")
    if variance < 200:
        issues.append("锐度不足/可能模糊")
    if mean < 30 or mean > 230:
        issues.append("曝光异常(过暗或过曝)")

    # 综合评分(0..1):分辨率 0.4 + 锐度 0.4 + 曝光 0.2
    res_score = min(1.0, w / max(min_width, 1))
    sharp_score = min(1.0, variance / 1500)
    exp_mid = abs(mean - 130) / 130  # 0=好,1=极差
    exp_score = max(0.0, 1.0 - exp_mid)
    score = round(0.4 * res_score + 0.4 * sharp_score + 0.2 * exp_score, 3)

    suggestion = ""
    if "分辨率不足" in "".join(issues):
        suggestion = "建议下载原图或调用 enhance 上采样"
    elif "锐度不足" in "".join(issues):
        suggestion = "建议替换为更清晰图,或调用 enhance"
    elif "曝光异常" in "".join(issues):
        suggestion = "建议调整曝光后再使用"

    return {
        "score": score,
        "issues": issues,
        "suggestion": suggestion,
        "width": w,
        "height": h,
        "sharpness": round(variance, 1),
        "brightness": round(mean, 1),
    }


async def quality_check(arguments: dict[str, Any]) -> dict[str, Any]:
    ref = arguments.get("ref") or arguments.get("oss_ref") or arguments.get("url")
    min_width = int(arguments.get("min_width", 720))
    if not ref:
        return {"error": "ref 必填", "_failed": True}
    try:
        return await asyncio.to_thread(_do_quality_check, str(ref), min_width)
    except Exception as e:
        log.warning("quality_check.failed", err=str(e))
        return {"score": 0.5, "issues": [str(e)], "suggestion": "", "_failed": True}


app = make_app(
    server_name="image-tools",
    tools={
        "concat_long": concat_long,
        "download_batch": download_batch,
        "bg_remove": bg_remove,
        "enhance": enhance,
        "quality_check": quality_check,
    },
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7002)
