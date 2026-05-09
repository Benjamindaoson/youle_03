"""Agent 4 tts_generate — 走 LiteLLM /v1/audio/speech 真生 mp3,落 OSS。

设计:
- 脚本文本先经 _preprocess_tts_text 清洗(移除舞台指示词 / Markdown 格式)
- LiteLLM 路由 task_type=tts_generate → Volcengine TTS / OpenAI TTS
- LITELLM_MOCK=true 返回最小有效 mp3 frame(避免下游 video_compose 崩)
- /v1/audio/speech 失败时退回占位 mp3 — 不阻塞下游(铁律 12 三层兜底之兜底)
- 产物 mp3 写 OSS,reference 用 oss:// 标识
"""

from __future__ import annotations

import re
import time
from uuid import uuid4

import structlog

from agents._common import llm
from agents._common.flywheel_emitter import emit
from agents._common.oss_writer import put_bytes
from agents._common.protocol import AgentResult, AgentTask, ArtifactRef

log = structlog.get_logger(__name__)

# 占位静音 mp3(LAME header + 1KB 静音 — ffmpeg 能识别为有效 audio)
_FALLBACK_SILENT_MP3 = b"\xff\xfb\x90\x00" + b"\x00" * 1024

# TTS 读出会很奇怪的模式
_STRIP_PATTERNS = [
    re.compile(r"\[镜头[^\]]*\]"),                    # [镜头一] [镜头二]
    re.compile(r"\[B-roll[^\]]*\]", re.IGNORECASE),   # [B-roll: ...]
    re.compile(r"\(B-roll[^)]*\)", re.IGNORECASE),    # (B-roll: ...)
    re.compile(r"\[场景[^\]]*\]"),                     # [场景描述]
    re.compile(r"\[画面[^\]]*\]"),                     # [画面:...]
    re.compile(r"【[^】]{1,20}】"),                    # 【口播】【字幕】等短标签
    re.compile(r"^#{1,6}\s+", re.MULTILINE),          # Markdown 标题 #/##/###
    re.compile(r"\*{1,2}([^*]+)\*{1,2}"),             # **bold** / *italic*
    re.compile(r"`[^`]+`"),                            # `code`
    re.compile(r"^\s*[-*]\s+", re.MULTILINE),          # Markdown 列表符号
    re.compile(r"\d+\.\s+(?=[^\d])"),                 # 1. 2. 有序列表前缀
]


def _preprocess_tts_text(text: str) -> str:
    """清洗脚本文本,使其适合 TTS 朗读。

    移除:场景指示词、Markdown 格式、括号内的导演注释。
    规范化:省略号、中英文标点混用。
    """
    for pat in _STRIP_PATTERNS:
        text = pat.sub("", text)

    # 移除括号内的纯英文/技术注释(如 (fade in) / (cut to))
    text = re.sub(r"\([A-Za-z ]{3,30}\)", "", text)

    # 规范化省略号
    text = text.replace("...", "……").replace("…", "……")

    # 多余空行压缩(保留最多一个换行作为段落间停顿)
    text = re.sub(r"\n{2,}", "\n", text)

    # 全角/半角混用标点统一(确保 TTS 停顿正确)
    text = text.replace(",", "，").replace(". ", "。").replace("! ", "！")

    return text.strip()


async def tts_generate_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()
    raw_text = task.inputs.get("text") or task.inputs.get("_prompt") or ""
    voice = task.parameters.get("voice", "female_warm")
    response_format = task.parameters.get("response_format", "mp3")
    skip_preprocess = bool(task.parameters.get("skip_preprocess", False))

    if not raw_text:
        return AgentResult(
            task_id=task.task_id,
            step_id=task.step_id,
            status="failed",
            error_detail={"reason": "missing_text"},
        )

    text = raw_text if skip_preprocess else _preprocess_tts_text(raw_text)
    if not text:
        text = raw_text  # 预处理后为空则回退原文

    audio_bytes: bytes
    model_used = "tts"
    try:
        audio_bytes = await llm.audio_speech(
            task_type="tts_generate",
            text=text,
            voice=voice,
            response_format=response_format,
            routing_hints=task.routing_hints,
        )
    except Exception as e:
        log.warning("tts_generate.audio_speech_failed_fallback", err=str(e))
        audio_bytes = _FALLBACK_SILENT_MP3
        model_used = "fallback_silence"

    key = f"artifacts/{task.task_id}/{task.step_id}.{response_format}"
    oss_ref = await put_bytes(
        key=key, data=audio_bytes, content_type=f"audio/{response_format}"
    )

    await emit(
        signal_type="trace",
        payload={
            "task_id": str(task.task_id),
            "step_id": task.step_id,
            "agent_id": "agent_4",
            "task_type": "tts_generate",
            "model": model_used,
            "raw_char_count": len(raw_text),
            "processed_char_count": len(text),
            "size_bytes": len(audio_bytes),
        },
    )

    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="completed",
        output=ArtifactRef(
            artifact_id=uuid4(),
            type="audio",
            reference=oss_ref,
            extra_metadata={
                "voice": voice,
                "raw_char_count": len(raw_text),
                "processed_char_count": len(text),
                "format": response_format,
                "size_bytes": len(audio_bytes),
                "model": model_used,
            },
        ),
        cost_usd=None,
        duration_ms=int((time.monotonic() - t0) * 1000),
        model_used=model_used,
    )
