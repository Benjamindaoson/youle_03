"""Agent 3 image_compose — PIL 多图层文字/徽章/价格标签/水印叠加。

支持的 layer 类型:
  text        — 任意文字,自定义位置/颜色/字号/背景
  badge       — 圆角色块徽章(默认红色 96110 反诈标识)
  price_tag   — 电商价格标签(橙色块 + 价格 + 副标签)
  watermark   — 半透明水印(支持单次或平铺)

position 预设:
  top-left / top-right / bottom-left / bottom-right(默认)
  center / top-center / bottom-center / custom(需配 x, y)

降级策略:
  - PIL 未安装 → 直接返回原图 ref(completed,不阻塞流程)
  - 图片加载失败 → 同上
  - 单个 layer 渲染报错 → 跳过该层,继续渲染其他层
"""

from __future__ import annotations

import asyncio
import io
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import structlog

from agents._common.flywheel_emitter import emit
from agents._common.oss_writer import put_bytes
from agents._common.protocol import AgentResult, AgentTask, ArtifactRef

log = structlog.get_logger(__name__)

_FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
]

_POSITION_FNS: dict[str, Any] = {
    "top-left":      lambda w, h, tw, th: (40, 40),
    "top-right":     lambda w, h, tw, th: (w - tw - 40, 40),
    "bottom-left":   lambda w, h, tw, th: (40, h - th - 40),
    "bottom-right":  lambda w, h, tw, th: (w - tw - 40, h - th - 40),
    "center":        lambda w, h, tw, th: ((w - tw) // 2, (h - th) // 2),
    "top-center":    lambda w, h, tw, th: ((w - tw) // 2, 40),
    "bottom-center": lambda w, h, tw, th: ((w - tw) // 2, h - th - 40),
}


def _load_font(size: int):
    try:
        from PIL import ImageFont
        for path in _FONT_CANDIDATES:
            if Path(path).exists():
                return ImageFont.truetype(path, size)
        return ImageFont.load_default()
    except Exception:
        return None


def _text_size(draw, text: str, font) -> tuple[int, int]:
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        return len(text) * (getattr(font, "size", 12) // 2 or 6), getattr(font, "size", 12)


def _resolve_xy(position_key: str, layer: dict, w: int, h: int, tw: int, th: int) -> tuple[int, int]:
    if position_key == "custom":
        return int(layer.get("x", 40)), int(layer.get("y", 40))
    fn = _POSITION_FNS.get(position_key, _POSITION_FNS["bottom-right"])
    return fn(w, h, tw, th)


def _apply_text_layer(draw, img_size: tuple[int, int], layer: dict) -> None:
    w, h = img_size
    text = str(layer.get("content", ""))
    if not text:
        return
    style = layer.get("style", {})
    font_size = int(style.get("font_size", 36))
    color = tuple(int(v) for v in style.get("color", [255, 255, 255]))
    padding = int(style.get("padding", 12))
    font = _load_font(font_size)
    tw, th = _text_size(draw, text, font)

    bg = style.get("bg_color")
    x, y = _resolve_xy(layer.get("position", "bottom-right"), layer, w, h, tw + padding * 2, th + padding * 2)

    if bg:
        bg_color = tuple(int(v) for v in bg)
        try:
            draw.rounded_rectangle([x, y, x + tw + padding * 2, y + th + padding * 2], radius=8, fill=bg_color)
        except AttributeError:
            draw.rectangle([x, y, x + tw + padding * 2, y + th + padding * 2], fill=bg_color)
    draw.text((x + padding, y + padding), text, font=font, fill=color)


def _apply_badge_layer(draw, img_size: tuple[int, int], layer: dict) -> None:
    w, h = img_size
    text = str(layer.get("content", "96110"))
    style = layer.get("style", {})
    font_size = int(style.get("font_size", 32))
    font = _load_font(font_size)
    bg_color = tuple(int(v) for v in style.get("bg_color", [220, 38, 38, 230]))
    text_color = tuple(int(v) for v in style.get("color", [255, 255, 255]))
    padding = 16

    tw, th = _text_size(draw, text, font)
    bw, bh = tw + padding * 2, th + padding * 2
    x, y = _resolve_xy(layer.get("position", "bottom-right"), layer, w, h, bw, bh)

    try:
        draw.rounded_rectangle([x, y, x + bw, y + bh], radius=bh // 2, fill=bg_color)
    except AttributeError:
        draw.rectangle([x, y, x + bw, y + bh], fill=bg_color)
    draw.text((x + padding, y + padding), text, font=font, fill=text_color)


def _apply_price_tag_layer(draw, img_size: tuple[int, int], layer: dict) -> None:
    w, h = img_size
    price = str(layer.get("content", ""))
    label = str(layer.get("label", ""))
    style = layer.get("style", {})
    font_price = _load_font(int(style.get("font_size", 52)))
    font_label = _load_font(int(style.get("label_font_size", 26)))
    bg_color = tuple(int(v) for v in style.get("bg_color", [255, 80, 0, 230]))
    text_color = tuple(int(v) for v in style.get("color", [255, 255, 255]))
    padding = 16

    pw, ph = _text_size(draw, price, font_price)
    lw, lh = (_text_size(draw, label, font_label) if label else (0, 0))

    tag_w = max(pw, lw) + padding * 2
    tag_h = ph + (lh + 6 if label else 0) + padding * 2
    x, y = _resolve_xy(layer.get("position", "bottom-left"), layer, w, h, tag_w, tag_h)

    try:
        draw.rounded_rectangle([x, y, x + tag_w, y + tag_h], radius=12, fill=bg_color)
    except AttributeError:
        draw.rectangle([x, y, x + tag_w, y + tag_h], fill=bg_color)

    cur_y = y + padding
    if label:
        draw.text((x + padding, cur_y), label, font=font_label, fill=text_color)
        cur_y += lh + 6
    draw.text((x + padding, cur_y), price, font=font_price, fill=text_color)


def _apply_watermark_layer(draw, img_size: tuple[int, int], layer: dict) -> None:
    w, h = img_size
    text = str(layer.get("content", ""))
    if not text:
        return
    style = layer.get("style", {})
    font_size = int(style.get("font_size", 24))
    opacity = min(255, max(0, int(style.get("opacity", 80))))
    color_base = list(style.get("color", [200, 200, 200]))
    color = tuple(color_base[:3] + [opacity])
    font = _load_font(font_size)

    if style.get("tile", False):
        step_x = int(style.get("tile_step_x", 220))
        step_y = int(style.get("tile_step_y", 160))
        for tx in range(0, w, step_x):
            for ty in range(0, h, step_y):
                draw.text((tx, ty), text, font=font, fill=color)
    else:
        tw, th = _text_size(draw, text, font)
        x, y = _resolve_xy(layer.get("position", "bottom-right"), layer, w, h, tw, th)
        draw.text((x, y), text, font=font, fill=color)


_LAYER_RENDERERS = {
    "text":       _apply_text_layer,
    "badge":      _apply_badge_layer,
    "price_tag":  _apply_price_tag_layer,
    "watermark":  _apply_watermark_layer,
}


def _load_image_bytes_sync(ref: str) -> bytes | None:
    """同步加载图片 bytes(供 asyncio.to_thread 调用)。"""
    try:
        if ref.startswith("oss://"):
            import boto3
            from botocore.client import Config
            s3 = boto3.client(
                "s3",
                endpoint_url=os.getenv("OSS_ENDPOINT", "http://localhost:9000"),
                aws_access_key_id=os.getenv("OSS_ACCESS_KEY", "minioadmin"),
                aws_secret_access_key=os.getenv("OSS_SECRET_KEY", "minioadmin"),
                config=Config(signature_version="s3v4"),
            )
            parsed = urlparse(ref)
            obj = s3.get_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))
            return obj["Body"].read()
        elif ref.startswith(("http://", "https://")):
            import httpx
            r = httpx.get(ref, timeout=15, follow_redirects=True)
            r.raise_for_status()
            return r.content
    except Exception as e:
        log.warning("image_compose.load_failed", ref=str(ref)[:60], err=str(e))
    return None


async def image_compose_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()
    image_ref = str(
        task.inputs.get("image_ref")
        or task.inputs.get("reference")
        or task.parameters.get("image_ref", "")
    )
    layers: list[dict] = list(
        task.inputs.get("layers") or task.parameters.get("layers") or []
    )

    if not image_ref:
        return AgentResult(
            task_id=task.task_id,
            step_id=task.step_id,
            status="failed",
            error_detail={"reason": "missing_image_ref"},
        )

    # 无 layers → 透传原图,不报错
    if not layers:
        log.info("image_compose.no_layers_passthrough", task_id=str(task.task_id))
        return AgentResult(
            task_id=task.task_id,
            step_id=task.step_id,
            status="completed",
            output=ArtifactRef(
                artifact_id=uuid4(),
                type="image",
                reference=image_ref,
                extra_metadata={"composed": False, "reason": "no_layers"},
            ),
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    composed_ref = image_ref
    size_bytes = 0
    composed = False

    try:
        from PIL import Image, ImageDraw  # noqa: F401

        raw = await asyncio.to_thread(_load_image_bytes_sync, image_ref)
        if raw is None:
            raise ValueError("cannot_load_base_image")

        img = Image.open(io.BytesIO(raw)).convert("RGBA")
        draw = ImageDraw.Draw(img, "RGBA")
        img_size = img.size

        for layer in layers:
            layer_type = layer.get("type", "text")
            renderer = _LAYER_RENDERERS.get(layer_type)
            if renderer is None:
                log.warning("image_compose.unknown_layer_type", layer_type=layer_type)
                continue
            try:
                renderer(draw, img_size, layer)
            except Exception as e:
                log.warning("image_compose.layer_error", layer_type=layer_type, err=str(e))

        output_format = str(task.parameters.get("output_format", "PNG")).upper()
        buf = io.BytesIO()
        img_out = img.convert("RGB") if output_format in ("JPEG", "JPG") else img
        img_out.save(buf, format="PNG" if output_format not in ("JPEG", "JPG", "WEBP") else output_format, quality=92)
        composed_bytes = buf.getvalue()
        size_bytes = len(composed_bytes)

        ext = "jpg" if output_format in ("JPEG", "JPG") else output_format.lower()
        key = f"artifacts/{task.task_id}/{task.step_id}_composed.{ext}"
        composed_ref = await put_bytes(key=key, data=composed_bytes, content_type=f"image/{ext}")
        composed = True

    except ImportError:
        log.warning("image_compose.pil_unavailable_passthrough")
    except Exception as e:
        log.warning("image_compose.failed_passthrough", err=str(e))

    layer_types = [layer.get("type", "text") for layer in layers]

    await emit(
        signal_type="trace",
        payload={
            "task_id": str(task.task_id),
            "step_id": task.step_id,
            "agent_id": "agent_3",
            "task_type": "image_compose",
            "layer_count": len(layers),
            "layer_types": layer_types,
            "composed": composed,
        },
    )

    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="completed",
        output=ArtifactRef(
            artifact_id=uuid4(),
            type="image",
            reference=composed_ref,
            extra_metadata={
                "composed": composed,
                "source_ref": image_ref,
                "layer_count": len(layers),
                "layer_types": layer_types,
                "size_bytes": size_bytes,
            },
        ),
        duration_ms=int((time.monotonic() - t0) * 1000),
    )
