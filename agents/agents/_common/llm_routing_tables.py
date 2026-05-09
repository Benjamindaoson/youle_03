"""task_type ↔ 模型主备路由表 — 独立模块以控制 `llm.py` 体积。

对齐 docs 模型路由附录;运行时仍由 LiteLLM / routing_hints 进一步覆盖。"""
from __future__ import annotations

import os
from typing import Any

IMAGE_GENERATION_MODEL = os.getenv("IMAGE_GENERATION_MODEL", "openai/gpt-5.4-image-2")
XHS_SEEDREAM_MODEL = os.getenv("XHS_SEEDREAM_MODEL", "bytedance-seed/seedream-3-0-250828")
XHS_NANO_BANANA_MODEL = os.getenv("XHS_NANO_BANANA_MODEL", "google/gemini-2.5-flash-image")
XHS_GPT_IMAGE_MODEL = os.getenv("XHS_GPT_IMAGE_MODEL", IMAGE_GENERATION_MODEL)

MODEL_ALIASES: dict[str, str] = {
    "gpt-image-2": "openai/gpt-5.4-image-2",
    "gpt-5": "openai/gpt-5",
    "gpt-5-mini": "openai/gpt-5-mini",
    "gpt-5-vision": "openai/gpt-5-mini",
    "gpt-5.5": "openai/gpt-5.5",
    "claude-haiku-4-5": "anthropic/claude-haiku-4.5",
    "claude-sonnet-4-6": "anthropic/claude-sonnet-4.6",
    "claude-sonnet-vision": "anthropic/claude-sonnet-4.6",
    "kimi-k2": "Pro/moonshotai/Kimi-K2.6",
    "kimi-k2.6": "Pro/moonshotai/Kimi-K2.6",
    "qwen3.6-plus": "Qwen/Qwen3.6-Plus",
    "volcengine-tts": "Qwen/Qwen3-Omni-30B-A3B-Instruct",
    "aliyun-tts": "Qwen/Qwen3-Omni-30B-A3B-Instruct",
    "whisper-v3": "Qwen/Qwen3-Omni-30B-A3B-Instruct",
    "aliyun-asr": "Qwen/Qwen3-Omni-30B-A3B-Instruct",
    "veo-3": "google/gemini-2.5-flash",
    "seedance-2": "bytedance-seed/seed-2.0-lite",
    "kling-2": "openrouter/auto",
}

AGENT_ROUTING: dict[str, dict[str, list[Any]]] = {
    "short_writing": {"primary": ["deepseek-v4-flash"], "fallback": ["deepseek-v4-pro"]},
    "long_writing": {"primary": ["kimi-k2"], "fallback": ["deepseek-v4-pro", "claude-sonnet-4-6"]},
    "structured_writing": {"primary": ["deepseek-v4-pro"], "fallback": ["kimi-k2"]},
    "short_video_script": {"primary": ["deepseek-v4-pro"], "fallback": ["kimi-k2", "claude-sonnet-4-6"]},
    "web_search": {"primary": ["claude-sonnet-4-6"], "fallback": ["gpt-5"]},
    "version_compare": {"primary": ["deepseek-v4-flash"], "fallback": ["kimi-k2"]},
    "image_generate": {"primary": [IMAGE_GENERATION_MODEL], "fallback": ["openai/gpt-5.4-image-2", "openrouter/auto"]},
    "batch_generate": {"primary": [IMAGE_GENERATION_MODEL], "fallback": ["openai/gpt-5.4-image-2", "openrouter/auto"]},
    "image_describe": {"primary": ["claude-sonnet-vision"], "fallback": ["gpt-5-vision"]},
    "image_quality_check": {"primary": ["gpt-5-vision"], "fallback": ["claude-sonnet-vision"]},
    "style_extract": {"primary": ["claude-sonnet-vision"], "fallback": ["gpt-5-vision"]},
    "xhs_cover_image": {"primary": [XHS_SEEDREAM_MODEL], "fallback": [XHS_NANO_BANANA_MODEL, XHS_GPT_IMAGE_MODEL]},
    "xhs_slide_text_image": {"primary": [XHS_GPT_IMAGE_MODEL], "fallback": [XHS_SEEDREAM_MODEL, XHS_NANO_BANANA_MODEL]},
    "xhs_product_image": {"primary": [XHS_SEEDREAM_MODEL], "fallback": [XHS_NANO_BANANA_MODEL, XHS_GPT_IMAGE_MODEL]},
    "xhs_ambience_image": {"primary": [XHS_NANO_BANANA_MODEL], "fallback": [XHS_SEEDREAM_MODEL, XHS_GPT_IMAGE_MODEL]},
    "xhs_series_image": {"primary": [XHS_NANO_BANANA_MODEL], "fallback": [XHS_GPT_IMAGE_MODEL, XHS_SEEDREAM_MODEL]},
    "xhs_local_edit_image": {"primary": [XHS_GPT_IMAGE_MODEL], "fallback": [XHS_SEEDREAM_MODEL, XHS_NANO_BANANA_MODEL]},
    "xhs_carousel_plan": {"primary": ["deepseek-v4-pro"], "fallback": ["deepseek-v4-flash", "kimi-k2"]},
    "xhs_carousel_copy": {"primary": ["deepseek-v4-pro"], "fallback": ["kimi-k2", "deepseek-v4-flash"]},
    "xhs_delivery_summary": {"primary": ["deepseek-v4-pro"], "fallback": ["deepseek-v4-flash"]},
    "tts_generate": {"primary": ["volcengine-tts"], "fallback": ["aliyun-tts"]},
    "audio_to_text": {"primary": ["whisper-v3"], "fallback": ["aliyun-asr"]},
    "bgm_select": {"primary": ["deepseek-v4-flash"], "fallback": ["kimi-k2"]},
    "text_to_video": {"primary": ["veo-3"], "fallback": ["seedance-2", "kling-2"]},
    "image_to_video": {"primary": ["seedance-2"], "fallback": ["kling-2"]},
}

COGNITIVE_TIER: dict[str, list[str]] = {
    "primary": [
        os.getenv("COGNITIVE_PRIMARY_MODEL", "claude-sonnet-4-6"),
    ],
    "fallback": [
        os.getenv("COGNITIVE_FALLBACK_MODEL", "gpt-5"),
        "kimi-k2",
    ],
}
