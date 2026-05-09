"""Agent 端 LLM 客户端(铁律 7:走 LiteLLM,禁止 import openai/anthropic)。

backend.app.router 是后端用的;Agent 进程独立,这里复制最小必要逻辑(同样行为)。
两边路由策略由 LiteLLM Proxy 集中管理;客户端只是 HTTP 包装。
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import httpx
import structlog

from agents._common.llm_routing_tables import (
    AGENT_ROUTING,
    COGNITIVE_TIER,
    IMAGE_GENERATION_MODEL,
    MODEL_ALIASES,
    XHS_GPT_IMAGE_MODEL,
    XHS_NANO_BANANA_MODEL,
    XHS_SEEDREAM_MODEL,
)

log = structlog.get_logger(__name__)

LITELLM_URL = os.getenv("LITELLM_URL", "http://litellm-proxy:4000")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "sk-mock-1234")
LITELLM_MOCK = os.getenv("LITELLM_MOCK", "true").lower() == "true"

OPENROUTER_API_BASE = os.getenv("OPENROUTER_API_BASE", LITELLM_URL)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", LITELLM_API_KEY)
DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
SILICONFLOW_API_BASE = os.getenv("SILICONFLOW_API_BASE", "https://api.siliconflow.cn/v1")
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")

# SSE 单行解析连续失败阈值;超过则中止流式以避免静默卡死。
_SSE_MAX_BAD_LINES = max(8, int(os.getenv("LLM_SSE_MAX_CONSEC_PARSE_FAILURES", "64")))


class LLMResponse:
    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw

    @property
    def content(self) -> str:
        return self.raw["choices"][0]["message"]["content"]

    @property
    def model(self) -> str:
        return self.raw.get("model", "unknown")

    @property
    def usage(self) -> dict[str, int]:
        return self.raw.get("usage", {})

    @property
    def cost_usd(self) -> float | None:
        return self.raw.get("response_cost")

    @property
    def fallback_used(self) -> bool:
        """True 表示本次请求由备选模型而非首选模型响应(质量可能有差异)。"""
        return bool(self.raw.get("_fallback_used"))


_http_clients: dict[tuple[str, str], httpx.AsyncClient] = {}


def _provider_for_model(model: str) -> tuple[str, str]:
    """按模型名选择 OpenAI-compatible provider。

    优先级:
    - gpt / claude / openai/* / anthropic/* / google/* / bytedance-seed/* / openrouter/* → OpenRouter
    - deepseek* → DeepSeek
    - 其他 → SiliconFlow
    """
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
    return SILICONFLOW_API_BASE, SILICONFLOW_API_KEY or LITELLM_API_KEY


def _resolve_model(model: str) -> str:
    return MODEL_ALIASES.get(model, model)


def _client(base_url: str, api_key: str) -> httpx.AsyncClient:
    key = (base_url.rstrip("/"), api_key)
    if key not in _http_clients:
        _http_clients[key] = httpx.AsyncClient(
            base_url=key[0],
            timeout=httpx.Timeout(120.0, connect=5.0),
            headers={"Authorization": f"Bearer {api_key}"},
        )
    return _http_clients[key]


def _chat_completions_path(base_url: str) -> str:
    return "/chat/completions" if base_url.rstrip("/").endswith("/v1") else "/v1/chat/completions"


def _push_models_from_hint(out: list[str], hint: Any) -> None:
    if hint is None:
        return
    if isinstance(hint, (list, tuple)):
        for item in hint:
            _push_models_from_hint(out, item)
        return
    s = str(hint).strip()
    if not s:
        return
    resolved = _resolve_model(s)
    if resolved not in out:
        out.append(resolved)


def _task_type_model_chain(task_type: str, routing_hints: dict[str, Any] | None) -> list[str]:
    """routing_hints 与 AGENT_ROUTING 合并为主→备单向链,dup 跳过。"""
    hints = routing_hints or {}
    table = AGENT_ROUTING.get(task_type, {})
    out: list[str] = []
    _push_models_from_hint(out, hints.get("primary"))
    _push_models_from_hint(out, table.get("primary"))
    _push_models_from_hint(out, hints.get("fallback"))
    _push_models_from_hint(out, table.get("fallback"))
    if not out:
        out.append(_resolve_model("deepseek-v4-flash"))
    return out


def _cognitive_model_chain(extra_routing_hints: dict[str, Any] | None) -> list[str]:
    hints = extra_routing_hints or {}
    out: list[str] = []
    _push_models_from_hint(out, hints.get("primary"))
    _push_models_from_hint(out, COGNITIVE_TIER["primary"])
    _push_models_from_hint(out, hints.get("fallback"))
    _push_models_from_hint(out, COGNITIVE_TIER["fallback"])
    if not out:
        out.append(_resolve_model("claude-sonnet-4-6"))
    return out


def _llm_fallback_worthy(exc: BaseException) -> bool:
    """判定是否应在主模型失败后尝试备选(网络错 / 限流 / 5xx)。

    4xx 中 408/425/429 也允许换路(网关差异)。
    """
    if isinstance(exc, httpx.RequestError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        c = exc.response.status_code
        if c >= 500:
            return True
        if c in {408, 425, 429}:
            return True
        return False
    return False


async def _post_chat_json_with_fallback(
    models: list[str], payload_without_model: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    """返回 (response_dict, fallback_used)。fallback_used=True 表示非首选模型响应。"""
    # M-3: 每次调用生成唯一 request_id,各模型重试共享同一 ID 以便日志追踪
    request_id = str(uuid.uuid4())
    last: BaseException | None = None
    for ix, model in enumerate(models):
        body = dict(payload_without_model)
        body["model"] = model
        base_url, api_key = _provider_for_model(model)
        try:
            log.debug(
                "agent.llm.chat_attempt",
                model=model,
                base_url=base_url,
                attempt=ix + 1,
                n_models=len(models),
                request_id=request_id,
            )
            resp = await _client(base_url, api_key).post(
                _chat_completions_path(base_url),
                json=body,
                headers={"X-Request-ID": request_id},
            )
            resp.raise_for_status()
            fallback_used = ix > 0
            if fallback_used:
                log.warning(
                    "agent.llm.fallback_succeeded",
                    primary_model=models[0],
                    actual_model=model,
                    attempt=ix + 1,
                )
            return resp.json(), fallback_used
        except Exception as e:
            last = e
            if ix == len(models) - 1 or not _llm_fallback_worthy(e):
                raise
            log.warning(
                "agent.llm.fallback",
                from_model=model,
                attempt=ix + 1,
                err_type=type(e).__name__,
                err=str(e)[:200],
            )
    raise last  # pragma: no cover


async def complete(
    *,
    task_type: str,
    messages: list[dict[str, Any]],
    routing_hints: dict[str, Any] | None = None,
    response_format: dict[str, str] | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> LLMResponse:
    models = _task_type_model_chain(task_type, routing_hints)
    primary = models[0]

    if LITELLM_MOCK:
        return LLMResponse(_mock_response(task_type, primary))

    payload_without: dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload_without["max_tokens"] = max_tokens
    if response_format:
        payload_without["response_format"] = response_format

    raw, fallback_used = await _post_chat_json_with_fallback(models, payload_without)
    raw["_fallback_used"] = fallback_used
    return LLMResponse(raw)


async def complete_chat(
    *,
    task_type: str,
    messages: list[dict[str, Any]],
    routing_hints: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = "auto",
    temperature: float = 0.35,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """非流式 Chat Completions,可选 tools / tool_choice — ReAct Worker 调用。

    返回原始 JSON(OpenAI-compatible),便于解析 tool_calls / usage / response_cost。
    """
    models = _task_type_model_chain(task_type, routing_hints)
    primary = models[0]

    if LITELLM_MOCK:
        return _mock_complete_chat(task_type=task_type, model=primary, messages=messages, tools=tools)

    payload_without: dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload_without["max_tokens"] = max_tokens
    if tools:
        payload_without["tools"] = tools
        if tool_choice is not None:
            payload_without["tool_choice"] = tool_choice

    log.debug(
        "agent.llm.complete_chat",
        task_type=task_type,
        models=models,
        has_tools=bool(tools),
    )
    raw, fallback_used = await _post_chat_json_with_fallback(models, payload_without)
    if fallback_used:
        raw["_fallback_used"] = True
    return raw


# ─────────────────────────────────────────────────────────────────
# 认知层(Cognitive Tier) — ADR-019
#
# 用途有限但极其影响质量:Planner / Replanner / Critic / Reflexion /
# 中断分类。这一层不按 task_type 路由 — 永远用最强模型(Opus / GPT-5),
# 用量小,占总成本预计 < 15%。
#
# 与 Worker 端的 AGENT_ROUTING 解耦:那张表是按 task_type 选执行模型,
# 这里的认知层是"思考层",必须强,否则 Plan 质量塌方,下游再便宜也白搭。
# ─────────────────────────────────────────────────────────────────


async def complete_cognitive(
    *,
    purpose: str,
    messages: list[dict[str, Any]],
    response_format: dict[str, str] | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    extra_routing_hints: dict[str, Any] | None = None,
) -> LLMResponse:
    """认知层调用 — 给 Planner / Critic / Reflexion 用。

    与 `complete()` 的核心区别:
      1. 不按 task_type 路由,永远用 COGNITIVE_TIER 主备
      2. 默认 temperature=0.2(规划/评审需要稳定性)
      3. `purpose` 仅做日志,便于按用途切片成本

    LITELLM_MOCK 下仍走 _mock_response(以 purpose 当 task_type),
    保证单测无外部依赖。
    """
    models = _cognitive_model_chain(extra_routing_hints)
    primary = models[0]

    if LITELLM_MOCK:
        return LLMResponse(_mock_response(purpose, primary))

    payload_without: dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload_without["max_tokens"] = max_tokens
    if response_format:
        payload_without["response_format"] = response_format

    log.info(
        "agent.llm.cognitive",
        purpose=purpose,
        models=models,
    )
    raw, fallback_used = await _post_chat_json_with_fallback(models, payload_without)
    raw["_fallback_used"] = fallback_used
    return LLMResponse(raw)


async def audio_speech(
    *,
    task_type: str,
    text: str,
    voice: str = "female_warm",
    response_format: str = "mp3",
    routing_hints: dict[str, Any] | None = None,
) -> bytes:
    """Volcengine TTS / OpenAI TTS 等走 LiteLLM /v1/audio/speech 端点。

    返回原始音频 bytes,调用方负责落 OSS。
    LITELLM_MOCK=true 时返回最小有效 mp3 frame(~1 KB),保证下游 pipeline 不崩。
    """
    if LITELLM_MOCK:
        # 最小 mp3 帧:LAME header 占位,长度足够 ffmpeg 识别为 audio
        return b"\xff\xfb\x90\x00" + b"\x00" * 1024

    models = _task_type_model_chain(task_type, routing_hints)
    last: BaseException | None = None
    for ix, model in enumerate(models):
        payload: dict[str, Any] = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": response_format,
        }
        base_url, api_key = _provider_for_model(model)
        path = "/audio/speech" if base_url.rstrip("/").endswith("/v1") else "/v1/audio/speech"
        log.debug(
            "agent.audio_speech",
            task_type=task_type,
            model=model,
            base_url=base_url,
            char_count=len(text),
            attempt=ix + 1,
        )
        try:
            resp = await _client(base_url, api_key).post(path, json=payload)
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            last = e
            if ix == len(models) - 1 or not _llm_fallback_worthy(e):
                raise
            log.warning(
                "agent.audio_speech.fallback",
                model=model,
                err_type=type(e).__name__,
                err=str(e)[:200],
            )
    raise last  # pragma: no cover


async def stream(
    *,
    task_type: str,
    messages: list[dict[str, Any]],
    routing_hints: dict[str, Any] | None = None,
    temperature: float = 0.7,
):
    """流式输出 — Agent 1 long_writing 用,逐 chunk yield。"""
    models = _task_type_model_chain(task_type, routing_hints)

    if LITELLM_MOCK:
        for chunk in [f"[mock-{task_type}] ", "段一。", "段二。", "段三。"]:
            yield chunk
        return

    last: BaseException | None = None
    for ix, primary in enumerate(models):
        base_url, api_key = _provider_for_model(primary)
        body = {"model": primary, "messages": messages, "temperature": temperature, "stream": True}
        try:
            async with _client(base_url, api_key).stream(
                "POST",
                _chat_completions_path(base_url),
                json=body,
            ) as resp:
                resp.raise_for_status()
                import json as _json

                bad_sse = 0
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if payload == "[DONE]" or not payload:
                        continue
                    try:
                        data = _json.loads(payload)
                        delta = (
                            ((data.get("choices") or [{}])[0] or {}).get("delta") or {}
                        ).get("content", "")
                        if isinstance(delta, str) and delta:
                            bad_sse = 0
                            yield delta
                    except Exception as e:
                        bad_sse += 1
                        log.warning(
                            "agent.llm.stream.sse_parse_failed",
                            task_type=task_type,
                            model=primary,
                            attempt=bad_sse,
                            err_type=type(e).__name__,
                            line_preview=payload[:200],
                        )
                        if bad_sse >= _SSE_MAX_BAD_LINES:
                            log.error(
                                "agent.llm.stream.sse_parse_circuit_break",
                                task_type=task_type,
                                model=primary,
                                threshold=_SSE_MAX_BAD_LINES,
                            )
                            raise RuntimeError(
                                f"SSE parse failed {bad_sse} times consecutively for {task_type!r}; "
                                "upstream format may be broken"
                            ) from e
            return
        except Exception as e:
            last = e
            if ix == len(models) - 1 or not _llm_fallback_worthy(e):
                raise
            log.warning(
                "agent.llm.stream.fallback",
                from_model=primary,
                attempt=ix + 1,
                err_type=type(e).__name__,
                err=str(e)[:200],
            )
    raise last  # pragma: no cover


def _mock_response(task_type: str, model: str) -> dict[str, Any]:
    if task_type == "web_search":
        body = '{"results": [{"title":"mock 反诈案例","url":"https://example.com/1","snippet":"..."}]}'
    elif task_type in {"long_writing", "short_video_script"}:
        body = (
            "【反诈视频脚本 - mock】\n"
            "钩子:你接到陌生电话,对方说你涉嫌洗钱,要求转账...\n"
            "案例:2026 年某地张大妈被骗 30 万。\n"
            "呼吁:遇陌生电话 96110 一键查询。"
        )
    elif task_type == "structured_writing":
        body = '[{"label":"主标题","content":"..."},{"label":"段二","content":"..."}]'
    elif task_type == "image_quality_check":
        body = '{"score": 0.85, "issues": [], "suggestion": ""}'
    else:
        body = f"[mock-{task_type}] result"
    return {
        "id": "chatcmpl-mock",
        "model": model,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": body}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 100, "total_tokens": 150},
        "response_cost": 0.0001,
    }


def _mock_complete_chat(
    *,
    task_type: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """两轮固定 ReAct Mock:先发 MCP tool_call,再给 agent_finish 调用。"""
    if not tools:
        return _mock_response(task_type, model)

    names = [t.get("function", {}).get("name") for t in tools if isinstance(t.get("function"), dict)]
    mcp_candidates = [
        n
        for n in names
        if n and (n.startswith("mcp_") or n.startswith("mcp_search_") or n.startswith("mcp_image_"))
    ]
    if not mcp_candidates:
        mcp_candidates = [n for n in names if n and n != "agent_finish" and not n.startswith("workflow_")]
    picked = ""
    if task_type == "web_search":
        picked = next((n for n in mcp_candidates if "web_search" in n), mcp_candidates[0] if mcp_candidates else "")
    elif task_type == "web_scrape":
        picked = next((n for n in mcp_candidates if "fetch" in n), mcp_candidates[0] if mcp_candidates else "")
    else:
        picked = mcp_candidates[0] if mcp_candidates else ""

    tool_turns = sum(1 for m in messages if m.get("role") == "tool")
    usage = {"prompt_tokens": 40, "completion_tokens": 20, "total_tokens": 60}

    user_blob = "\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "user")
    query = user_blob[-300:] if user_blob else "mock-query"

    workflow_names = [n for n in names if n and n.startswith("workflow_")]

    if tool_turns == 0:
        fname = ""
        args: dict[str, Any] = {}
        if workflow_names:
            fname = workflow_names[0]
        elif task_type == "image_download" and mcp_candidates:
            fname = next((n for n in mcp_candidates if "download" in n), mcp_candidates[0])
            args = {"urls": ["https://picsum.photos/200"], "check_quality": False}
        elif mcp_candidates:
            fname = picked or mcp_candidates[0]
            if "web_search" in fname:
                args = {"query": query[:260], "max_results": int(min(12, len(query) % 15 + 3))}
            elif "web_fetch" in fname or "fetch" in fname:
                args = {"url": "https://example.com", "render_js": False}
        elif names and names[0] == "agent_finish":
            fname = "agent_finish"
            args = {
                "artifact_type": "text",
                "status": "completed",
                "markdown": f"[mock-direct:{task_type}] {query[:1800]}",
            }
        else:
            fname = (picked or (names[0] if names else "") or "agent_finish")
            if fname == "agent_finish":
                args = {
                    "artifact_type": "text",
                    "status": "completed",
                    "markdown": f"[mock-fallback:{task_type}]",
                }

        return {
            "id": "chatcmpl-mock-tools-round1",
            "model": model,
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_mock_1",
                                "type": "function",
                                "function": {"name": fname, "arguments": json.dumps(args, ensure_ascii=False)},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": usage,
            "response_cost": 0.0,
        }

    # 第二轮 → agent_finish(若注册了该工具);否则给出普通文本收尾
    if "agent_finish" in names:
        finish_body = {
            "artifact_type": "structured" if task_type == "web_search" else "text",
            "status": "completed",
            "markdown": f"[mock-react:{task_type}]\n{user_blob[:2000]}",
            "structured_payload": {"task_type": task_type, "_mock_finish": True}
            if task_type == "web_search"
            else None,
            "cost_note": "",
        }
        return {
            "id": "chatcmpl-mock-tools-finish",
            "model": model,
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_mock_finish",
                                "type": "function",
                                "function": {
                                    "name": "agent_finish",
                                    "arguments": json.dumps(
                                        {k: v for k, v in finish_body.items() if v is not None},
                                        ensure_ascii=False,
                                    ),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": usage,
            "response_cost": 0.0,
        }

    return _mock_response(task_type, model)


async def aclose() -> None:
    for client in _http_clients.values():
        await client.aclose()
    _http_clients.clear()
