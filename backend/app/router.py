"""LiteLLM 客户端封装(铁律 7 / ADR-007)。

铁律:禁止 `import openai` / `import anthropic`。所有模型调用走 `app.router.complete`。

dev 环境(LITELLM_MOCK=True)走 mock-litellm 容器,返回固定文本。
"""

from __future__ import annotations

import os
from typing import Any, Literal

import httpx
import structlog

from app.config import settings

log = structlog.get_logger(__name__)

OPENROUTER_API_BASE = os.getenv("OPENROUTER_API_BASE", settings.LITELLM_URL)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", settings.LITELLM_API_KEY)
DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
SILICONFLOW_API_BASE = os.getenv("SILICONFLOW_API_BASE", "https://api.siliconflow.cn/v1")
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")

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

# 路由策略:task_type → 主备模型(详见 docs/4_附录/模型路由表.md)
TASK_TYPE_ROUTING: dict[str, dict[str, list[str]]] = {
    # ── L1 编排层 ──
    "intent_understanding": {"primary": ["deepseek-v4-flash"], "fallback": ["claude-haiku-4-5", "gpt-5-mini"]},
    "skill_matching": {"primary": ["deepseek-v4-flash"], "fallback": ["claude-haiku-4-5"]},
    "interrupt_classification": {"primary": ["deepseek-v4-flash"], "fallback": ["claude-haiku-4-5", "gpt-5-mini"]},
    "brief_update": {"primary": ["deepseek-v4-flash"], "fallback": ["claude-haiku-4-5"]},
    "hitl_decision_parsing": {"primary": ["deepseek-v4-flash"], "fallback": ["claude-haiku-4-5"]},
    "rollback_target_compute": {"primary": ["deepseek-v4-flash"], "fallback": ["claude-haiku-4-5"]},
    "mcp_tool_decision": {"primary": ["deepseek-v4-flash"], "fallback": ["claude-haiku-4-5"]},
    "work_mode_switch": {"primary": ["deepseek-v4-flash"], "fallback": ["claude-haiku-4-5"]},

    # ── L2 文字 ──
    "short_writing": {"primary": ["deepseek-v4-flash"], "fallback": ["deepseek-v4-pro", "claude-haiku-4-5"]},
    "long_writing": {"primary": ["kimi-k2"], "fallback": ["deepseek-v4-pro", "claude-sonnet-4-6"]},
    "structured_writing": {"primary": ["deepseek-v4-pro"], "fallback": ["kimi-k2", "claude-sonnet-4-6"]},
    "short_video_script": {"primary": ["deepseek-v4-pro"], "fallback": ["kimi-k2", "claude-sonnet-4-6"]},
    "short_video_hook": {"primary": ["claude-sonnet-4-6"], "fallback": ["gpt-5", "deepseek-v4-pro"]},
    "web_search": {"primary": ["claude-sonnet-4-6"], "fallback": ["gpt-5"]},
    "version_compare": {"primary": ["deepseek-v4-flash"], "fallback": ["kimi-k2"]},
    "summarization": {"primary": ["deepseek-v4-flash"], "fallback": ["kimi-k2"]},
    "analysis": {"primary": ["claude-sonnet-4-6"], "fallback": ["deepseek-v4-pro", "gpt-5"]},
    "translation": {"primary": ["deepseek-v4-pro"], "fallback": ["kimi-k2"]},
    "polish": {"primary": ["deepseek-v4-flash"], "fallback": ["kimi-k2"]},
    "extraction": {"primary": ["deepseek-v4-flash"], "fallback": ["claude-haiku-4-5"]},

    # ── L2 图 ──
    "image_generate": {
        "primary": [settings.IMAGE_GENERATION_MODEL],
        "fallback": ["openai/gpt-5.4-image-2", "openrouter/auto"],
    },
    "batch_generate": {
        "primary": [settings.IMAGE_GENERATION_MODEL],
        "fallback": ["openai/gpt-5.4-image-2", "openrouter/auto"],
    },
    "image_describe": {"primary": ["claude-sonnet-vision"], "fallback": ["gpt-5-vision"]},
    "image_quality_check": {"primary": ["gpt-5-vision"], "fallback": ["claude-sonnet-vision"]},
    "style_extract": {"primary": ["claude-sonnet-vision"], "fallback": ["gpt-5-vision"]},

    # ── L2 影音 ──
    "text_to_video": {"primary": ["veo-3"], "fallback": ["seedance-2", "kling-2"]},
    "image_to_video": {"primary": ["seedance-2"], "fallback": ["kling-2", "veo-3"]},
    "tts_generate": {"primary": ["volcengine-tts"], "fallback": ["aliyun-tts"]},
    "audio_to_text": {"primary": ["whisper-v3"], "fallback": ["aliyun-asr"]},
}


class LLMResponse(dict):  # type: ignore[type-arg]
    """LiteLLM 风格的响应,模型 / 内容 / token 用量。"""

    @property
    def content(self) -> str:
        return self["choices"][0]["message"]["content"]


class _LiteLLMClient:
    def __init__(self) -> None:
        self._clients: dict[tuple[str, str], httpx.AsyncClient] = {}

    @staticmethod
    def _provider_for_model(model: str) -> tuple[str, str]:
        normalized = model.lower()
        if (
            normalized.startswith(("gpt", "openai/"))
            or "claude" in normalized
            or normalized.startswith("anthropic/")
            or normalized.startswith(("google/", "bytedance-seed/", "openrouter/"))
        ):
            return OPENROUTER_API_BASE, OPENROUTER_API_KEY
        if normalized.startswith("deepseek"):
            return DEEPSEEK_API_BASE, DEEPSEEK_API_KEY
        return SILICONFLOW_API_BASE, SILICONFLOW_API_KEY or settings.LITELLM_API_KEY

    @staticmethod
    def _resolve_model(model: str) -> str:
        return MODEL_ALIASES.get(model, model)

    def _client(self, base_url: str, api_key: str) -> httpx.AsyncClient:
        key = (base_url.rstrip("/"), api_key)
        if key not in self._clients:
            self._clients[key] = httpx.AsyncClient(
                base_url=key[0],
                timeout=httpx.Timeout(60.0, connect=5.0),
                headers={"Authorization": f"Bearer {api_key}"},
            )
        return self._clients[key]

    @staticmethod
    def _chat_completions_path(base_url: str) -> str:
        return "/chat/completions" if base_url.rstrip("/").endswith("/v1") else "/v1/chat/completions"

    async def complete(
        self,
        *,
        task_type: str,
        messages: list[dict[str, Any]],
        routing_hints: dict[str, Any] | None = None,
        response_format: dict[str, str] | None = None,
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """统一入口。task_type 决定模型路由,routing_hints 可手动覆盖。"""
        routing = TASK_TYPE_ROUTING.get(task_type, {})
        primary = self._resolve_model(
            (routing_hints or {}).get("primary") or (routing.get("primary") or ["deepseek-v4-flash"])[0]
        )

        payload: dict[str, Any] = {
            "model": primary,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_format:
            payload["response_format"] = response_format
        if stream:
            payload["stream"] = True

        base_url, api_key = self._provider_for_model(primary)
        log.debug("litellm.complete", task_type=task_type, model=primary, base_url=base_url)
        resp = await self._client(base_url, api_key).post(
            self._chat_completions_path(base_url),
            json=payload,
        )
        resp.raise_for_status()
        return LLMResponse(resp.json())

    async def aclose(self) -> None:
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()


class _MockClient:
    """dev / 离线测试用。返回固定文本,不发网络请求。"""

    async def complete(
        self,
        *,
        task_type: str,
        messages: list[dict[str, Any]],
        routing_hints: dict[str, Any] | None = None,
        response_format: dict[str, str] | None = None,
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        log.debug("mock.complete", task_type=task_type)
        body = "{\"intent_type\":\"task_request\",\"domain\":\"video\",\"scenario\":\"short_video\",\"confidence\":0.9}"
        if (response_format or {}).get("type") != "json_object":
            body = f"[mock-{task_type}] 这是 mock 模型返回的固定文本。"
        return LLMResponse(
            {
                "id": "chatcmpl-mock-001",
                "object": "chat.completion",
                "model": (routing_hints or {}).get("primary", "deepseek-v4-flash"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": body},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            }
        )

    async def aclose(self) -> None:
        pass


_singleton: _LiteLLMClient | _MockClient | None = None


def _get_client() -> _LiteLLMClient | _MockClient:
    global _singleton
    if _singleton is None:
        _singleton = _MockClient() if settings.LITELLM_MOCK else _LiteLLMClient()
    return _singleton


async def complete(
    *,
    task_type: str,
    messages: list[dict[str, Any]],
    routing_hints: dict[str, Any] | None = None,
    response_format: dict[str, str] | None = None,
    stream: bool = False,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> LLMResponse:
    return await _get_client().complete(
        task_type=task_type,
        messages=messages,
        routing_hints=routing_hints,
        response_format=response_format,
        stream=stream,
        temperature=temperature,
        max_tokens=max_tokens,
    )


async def close() -> None:
    global _singleton
    if _singleton is not None:
        await _singleton.aclose()
        _singleton = None


# 类型别名导出
ModelRole = Literal["system", "user", "assistant", "tool"]
