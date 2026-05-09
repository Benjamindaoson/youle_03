"""小红书图文 — Agent3 图模路由:按场景选择 Seedream / Nano Banana / GPT-Image-2 及各自 fallback 条件。

模型 ID 由 LiteLLM Proxy 解析;本地通过环境变量覆盖默认值。

设计要点:
1. 视觉场景 -> 模型链路映射(XHS_VISUAL_CHAINS),每条链按主/备/兜底排序。
2. 失败检测分两层:
   - HTTP 层(_http_should_fallback): 超时、5xx、429 一律 fallback;
     4xx 仅在命中明确的合规/限流/审计正则时才 fallback,避免无谓重试。
   - 文本层(_text_signals_failure): 处理「HTTP 200 但内容是错误页」的场景,
     例如 Seedream 因语言不支持返回的英文错误信息。
3. 整条链有总超时上界,防止下游慢调用拖垮上游 SLA。
4. 失败时通过 XHSChainError 把 trail 和 last_exc 一并抛出,上层可做归因。
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

import httpx
import structlog

from agents._common import llm
from agents._common.llm import LLMResponse

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# 常量与配置
# ---------------------------------------------------------------------------

# 文本失败检测:超过此长度认为是正常长文本响应,跳过关键词扫描(避免误判 + 性能)
_TEXT_FAILURE_MAX_LEN = 8000
# 短错误页阈值:短于此长度且不含 URL/对象路径,才考虑判定为错误页
_SHORT_ERROR_PAGE_MAX_LEN = 400
# HTTP 响应体读取上限,避免大响应体扫描成本
_RESPONSE_BODY_PEEK_LEN = 2000
# 整条 chain 的总超时预算(秒);3 个模型 * 单次 30s ≈ 90s 上界
_TOTAL_CHAIN_TIMEOUT_SEC = 90.0
# 错误片段在 trail / 日志中的截断长度
_ERR_SNIPPET_MAX = 400
_CONTENT_SNIPPET_MAX = 240

# 逻辑槽位 → 实际请求 model 名(经 LiteLLM)
_PROVIDERS: dict[str, str] = {
    "seedream": os.getenv("XHS_SEEDREAM_MODEL", "bytedance-seed/seedream-3-0-250828"),
    "nano_banana": os.getenv("XHS_NANO_BANANA_MODEL", "google/gemini-2.5-flash-image"),
    "gpt_image_2": os.getenv("XHS_GPT_IMAGE_MODEL", llm.IMAGE_GENERATION_MODEL),
}

# 视觉场景 → 调用顺序(主 → fallback1 → fallback2)
XHS_VISUAL_CHAINS: dict[str, list[str]] = {
    "cover": ["seedream", "nano_banana", "gpt_image_2"],
    "slide_text": ["gpt_image_2", "seedream", "nano_banana"],
    "product_realistic": ["seedream", "nano_banana", "gpt_image_2"],
    "ambience": ["nano_banana", "seedream", "gpt_image_2"],
    "series": ["nano_banana", "gpt_image_2", "seedream"],
    "local_edit": ["gpt_image_2", "seedream", "nano_banana"],
}

TASK_TYPE_TO_KIND: dict[str, str] = {
    "xhs_cover_image": "cover",
    "xhs_slide_text_image": "slide_text",
    "xhs_product_image": "product_realistic",
    "xhs_ambience_image": "ambience",
    "xhs_series_image": "series",
    "xhs_local_edit_image": "local_edit",
}


# ---------------------------------------------------------------------------
# 失败模式正则
#
# 设计原则:用具体的错误短语而非裸关键词,避免业务文本误判。
# 例如不要用裸 `policy`(用户 prompt 可能涉及"隐私政策海报"),
# 而要用 `policy violation` / `violates policy` 这种明确的错误片段。
# ---------------------------------------------------------------------------

_RE_SEEDREAM_AUDIT = re.compile(
    r"不符合规则|审核拒绝|内容违规|内容不符合|敏感内容|"
    r"non[-\s]?chinese|not\s+chinese|language\s+not\s+supported|english\s+only|"
    r"版式错误|layout\s+(error|invalid)",
    re.I,
)

_RE_NANO_LIMIT = re.compile(
    r"\b429\b|rate[\s_-]?limit|throttled?|throttling|quota\s+(exceeded|exhausted)|"
    r"内容不符合|内容安全|policy\s+violation|violates?\s+policy",
    re.I,
)

_RE_GPT_LIMIT = re.compile(
    r"\b429\b|rate[\s_-]?limit|throttled?|throttling|"
    r"内容不符合|moderation|content[_\s]policy|policy\s+violation|violates?\s+policy",
    re.I,
)

_PROVIDER_PATTERNS: dict[str, re.Pattern[str]] = {
    "seedream": _RE_SEEDREAM_AUDIT,
    "nano_banana": _RE_NANO_LIMIT,
    "gpt_image_2": _RE_GPT_LIMIT,
}


# ---------------------------------------------------------------------------
# 异常类型
# ---------------------------------------------------------------------------


class XHSChainError(RuntimeError):
    """整条 chain 走完仍未拿到可用响应。

    调用方可读 `trail` 看每一步的尝试结果,读 `cause` 看最后一次的底层异常。
    """

    def __init__(
        self,
        message: str,
        trail: list[dict[str, Any]],
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.trail = trail
        self.cause = cause

    def __str__(self) -> str:
        base = super().__str__()
        return f"{base} | trail={self.trail}"


# ---------------------------------------------------------------------------
# 启动时配置自检:防止 chain 引用了未定义的 slot
# ---------------------------------------------------------------------------


def _validate_config() -> None:
    for kind, chain in XHS_VISUAL_CHAINS.items():
        if not chain:
            raise RuntimeError(f"XHS chain {kind!r} is empty")
        for slot in chain:
            if slot not in _PROVIDERS:
                raise RuntimeError(
                    f"XHS chain {kind!r} references unknown slot {slot!r}; "
                    f"known slots: {sorted(_PROVIDERS)}"
                )


_validate_config()


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------


def resolve_visual_kind(task_type: str, parameters: dict[str, Any] | None) -> str:
    """从 task_type / parameters 中解析视觉场景类型。

    优先使用 parameters["xhs_visual_kind"](允许调用方显式覆盖),
    否则回退到 TASK_TYPE_TO_KIND 映射。未知 task_type 默认走 `cover` 链,
    但会打 warning 提示注册映射缺失。
    """
    p = parameters or {}
    explicit = p.get("xhs_visual_kind")
    if isinstance(explicit, str) and explicit in XHS_VISUAL_CHAINS:
        return explicit

    kind = TASK_TYPE_TO_KIND.get(task_type)
    if kind is None:
        log.warning(
            "xhs_image.unknown_task_type",
            task_type=task_type,
            fallback_kind="cover",
            hint="add mapping in TASK_TYPE_TO_KIND",
        )
        return "cover"
    return kind


def chain_for_kind(kind: str) -> list[str]:
    """返回某场景的模型调用链(只读副本,防止上游误改)。"""
    return list(XHS_VISUAL_CHAINS.get(kind, XHS_VISUAL_CHAINS["cover"]))


# ---------------------------------------------------------------------------
# 失败检测内部函数
# ---------------------------------------------------------------------------


def _model_id(slot: str) -> str:
    mid = _PROVIDERS.get(slot, slot)
    return llm.MODEL_ALIASES.get(mid, mid)


def _safe_response_body(resp: httpx.Response) -> str:
    """安全读取响应体片段,失败时返回空串。"""
    try:
        return resp.text[:_RESPONSE_BODY_PEEK_LEN]
    except Exception:
        return ""


def _text_matches_provider_pattern(text: str, provider: str) -> bool:
    """文本是否命中该 provider 的合规/限流/审计错误特征。"""
    pattern = _PROVIDER_PATTERNS.get(provider)
    if pattern is None:
        return False
    return bool(pattern.search(text))


def _text_signals_failure(content: str | None, provider: str) -> bool:
    """检测「HTTP 200 但内容是错误页/拒绝信息」。

    分两条路径:
    1. 命中 provider 专属错误正则 → 直接判失败。
    2. (仅 seedream)短文本 + 不含 URL/OSS 路径 + 含明确英文错误标记 → 判失败。
       注意:不再使用裸语言代码(en/fr/de/ja/ko)做启发,因为会误伤合法长文本。
    """
    if not content:
        return False
    if len(content) > _TEXT_FAILURE_MAX_LEN:
        return False

    if _text_matches_provider_pattern(content, provider):
        return True

    # Seedream 的英文错误页通常很短且形如 "Error: language not supported."
    # 上面的正则已经覆盖了 "language not supported" / "english only" 等明确措辞,
    # 不再额外做裸语言代码启发(误判率太高)。
    return False


def _http_should_fallback(exc: BaseException, provider: str) -> bool:
    """决定 HTTP 异常是否应触发 fallback 到下一个模型。

    策略:
    - 网络/超时/连接错误 → fallback(下游可能临时不可用)
    - 5xx → fallback(服务端故障,换一家)
    - 429 → fallback(限流,换一家)
    - 4xx(400/403/422):仅在响应体命中合规/限流正则时 fallback;
      否则视为「请求本身有问题」抛给上层,避免对 3 个模型重复发同样的坏请求。
    """
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)):
        return True

    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 429 or 500 <= code < 600:
            return True
        if code in {400, 403, 422}:
            body = _safe_response_body(exc.response)
            return _text_matches_provider_pattern(body, provider)

    return False


# ---------------------------------------------------------------------------
# 主入口:执行链路
# ---------------------------------------------------------------------------


async def generate_with_xhs_model_chain(
    *,
    logical_task_type: str,
    messages: list[dict[str, Any]],
    visual_kind: str,
    base_routing_hints: dict[str, Any] | None,
    temperature: float = 0.55,
    max_tokens: int | None = None,
) -> tuple[LLMResponse, list[dict[str, Any]]]:
    """按小红书策略依次尝试模型,返回首个「看似成功」的响应与尝试轨迹。

    Raises:
        XHSChainError: 整条链均未拿到可用响应。trail 记录每一步,cause 是最后一次底层异常。
        其他 httpx 异常: 当 4xx 不应 fallback 时(参数错误/鉴权失败等),原样抛出。
    """
    chain = chain_for_kind(visual_kind)
    trail: list[dict[str, Any]] = []
    last_exc: BaseException | None = None

    log.info(
        "xhs_image.chain_start",
        agent="agent_3",
        task_type=logical_task_type,
        visual_kind=visual_kind,
        chain=chain,
    )

    try:
        async with asyncio.timeout(_TOTAL_CHAIN_TIMEOUT_SEC):
            for slot in chain:
                model_id = _model_id(slot)
                hints = {**(base_routing_hints or {}), "primary": model_id}
                attempt_ctx = {
                    "agent": "agent_3",
                    "task_type": logical_task_type,
                    "visual_kind": visual_kind,
                    "slot": slot,
                    "model": model_id,
                }

                try:
                    resp = await llm.complete(
                        task_type=logical_task_type,
                        messages=messages,
                        routing_hints=hints,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                except (
                    httpx.HTTPStatusError,
                    httpx.TimeoutException,
                    httpx.RequestError,
                ) as e:
                    last_exc = e
                    err_snippet = str(e)[:_ERR_SNIPPET_MAX]
                    if _http_should_fallback(e, slot):
                        trail.append(
                            {**attempt_ctx, "outcome": "http_fallback", "err": err_snippet}
                        )
                        log.warning("xhs_image.fallback_http", **attempt_ctx, err=err_snippet)
                        continue
                    trail.append(
                        {**attempt_ctx, "outcome": "fatal_http", "err": err_snippet}
                    )
                    log.error("xhs_image.fatal_http", **attempt_ctx, err=err_snippet)
                    # 4xx 参数错误/鉴权类:原样抛出,让上层看到精确错误
                    raise
                except Exception as e:
                    err_snippet = str(e)[:_ERR_SNIPPET_MAX]
                    trail.append(
                        {**attempt_ctx, "outcome": "fatal_other", "err": err_snippet}
                    )
                    log.error(
                        "xhs_image.fatal_other",
                        **attempt_ctx,
                        err=err_snippet,
                        exc_info=True,
                    )
                    # 把 trail 附带到异常上,即使原异常被 raise,上层也能拿到上下文
                    if hasattr(e, "add_note"):
                        try:
                            e.add_note(f"xhs chain trail: {trail}")
                        except Exception:
                            pass
                    raise

                # —— 拿到响应,做文本层失败检测 ——
                content = resp.content if isinstance(resp.content, str) else ""
                if _text_signals_failure(content, slot):
                    trail.append(
                        {
                            **attempt_ctx,
                            "outcome": "soft_reject",
                            "snippet": content[:_CONTENT_SNIPPET_MAX],
                        }
                    )
                    log.info(
                        "xhs_image.fallback_soft",
                        **attempt_ctx,
                        snippet=content[:_CONTENT_SNIPPET_MAX],
                    )
                    continue

                trail.append({**attempt_ctx, "outcome": "ok"})
                log.info("xhs_image.chain_ok", **attempt_ctx, attempts=len(trail))
                return resp, trail

    except asyncio.TimeoutError as e:
        log.error(
            "xhs_image.chain_timeout",
            agent="agent_3",
            task_type=logical_task_type,
            visual_kind=visual_kind,
            budget_sec=_TOTAL_CHAIN_TIMEOUT_SEC,
            trail=trail,
        )
        raise XHSChainError(
            f"xhs chain timeout after {_TOTAL_CHAIN_TIMEOUT_SEC}s",
            trail,
            cause=e,
        ) from e

    # 链路走完,所有 slot 都返回了 soft_reject 或 http_fallback
    log.error(
        "xhs_image.chain_exhausted",
        agent="agent_3",
        task_type=logical_task_type,
        visual_kind=visual_kind,
        trail=trail,
    )
    raise XHSChainError("xhs chain exhausted", trail, cause=last_exc)