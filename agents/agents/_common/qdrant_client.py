"""轻量 Qdrant 客户端 — 仅供 episode_retrieval 用(ADR-011 / ADR-019)。

# 为什么不直接用 qdrant-client SDK
- 减少依赖面 — httpx 已在 pyproject 里,够用
- 我们只需要 1 个端点:`POST /collections/{name}/points/search`
- 嵌入也走 LiteLLM(铁律 7),不依赖 SDK 内置 embedder

# Graceful degradation
任何异常 / 配置缺失 / 服务不可达 → 返回空,**调用方应将其视为"没有历史经验"**,
继续走当前流程。critic 一样的设计哲学:基础设施挂不能让主流程崩。

# 与 backend 的 schema 对齐(ADR-011)
backend 写入 `workflow_traces` collection 时的 payload 形如:

    {
      "task_id": "...",
      "user_id": "...",
      "user_request": "...",         # 原文
      "plan_summary": "...",         # 步骤精简描述
      "outcome": "success|failed|partial",
      "user_rating": 0.92,           # nullable
      "duration_s": 320,
      "cost_usd": 0.045,
      "skill_id": "anti_fraud_video", # nullable(动态 plan 时为 null)
      "ts": "2026-05-09T12:34:56Z",
    }

S2 backend 把这部分对齐时如有变动,**只需调整 `EpisodePayload` 的字段映射**,
查询逻辑不需要动。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from agents._common.llm import (
    LITELLM_API_KEY,
    LITELLM_MOCK,
    LITELLM_URL,
)

log = structlog.get_logger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
WORKFLOW_TRACES_COLLECTION = os.getenv(
    "QDRANT_WORKFLOW_TRACES_COLLECTION", "workflow_traces"
)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-m3")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))  # bge-m3 default
QDRANT_TIMEOUT_S = float(os.getenv("QDRANT_TIMEOUT_S", "5"))


_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        headers = {}
        if QDRANT_API_KEY:
            headers["api-key"] = QDRANT_API_KEY
        _client = httpx.AsyncClient(
            base_url=QDRANT_URL.rstrip("/"),
            timeout=httpx.Timeout(QDRANT_TIMEOUT_S, connect=2.0),
            headers=headers,
        )
    return _client


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ─────────────────────────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────────────────────────
@dataclass
class EpisodePayload:
    """来自 Qdrant `workflow_traces` collection 的一条命中。

    字段对齐 ADR-011 的 backend 写入格式,容错读取(用 .get + 默认值)。
    """

    task_id: str
    user_request: str
    plan_summary: str
    outcome: str
    user_rating: float | None
    duration_s: int | None
    cost_usd: float | None
    score: float  # qdrant 给的相似度分

    @classmethod
    def from_qdrant_hit(cls, hit: dict[str, Any]) -> "EpisodePayload":
        payload = hit.get("payload") or {}
        return cls(
            task_id=str(payload.get("task_id") or hit.get("id") or ""),
            user_request=str(payload.get("user_request") or "")[:500],
            plan_summary=str(payload.get("plan_summary") or "")[:1000],
            outcome=str(payload.get("outcome") or "unknown"),
            user_rating=_to_float(payload.get("user_rating")),
            duration_s=_to_int(payload.get("duration_s")),
            cost_usd=_to_float(payload.get("cost_usd")),
            score=float(hit.get("score") or 0.0),
        )


# ─────────────────────────────────────────────────────────────────
# Embedding(走 LiteLLM /embeddings 端点)
# ─────────────────────────────────────────────────────────────────
async def embed_text(text: str) -> list[float] | None:
    """生成查询向量。

    LITELLM_MOCK=true 时返回 None — 调用方应跳过 search。
    任何异常 → None(graceful)。
    """
    if LITELLM_MOCK:
        return None

    try:
        async with httpx.AsyncClient(
            base_url=LITELLM_URL.rstrip("/"),
            timeout=httpx.Timeout(10.0, connect=2.0),
            headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
        ) as c:
            path = (
                "/embeddings"
                if LITELLM_URL.rstrip("/").endswith("/v1")
                else "/v1/embeddings"
            )
            resp = await c.post(
                path,
                json={"model": EMBEDDING_MODEL, "input": text[:8000]},
            )
            resp.raise_for_status()
            data = resp.json()
        emb = data.get("data", [{}])[0].get("embedding")
        if not isinstance(emb, list):
            log.warning("qdrant.embed.bad_shape", model=EMBEDDING_MODEL)
            return None
        return [float(x) for x in emb]
    except Exception as e:
        log.warning("qdrant.embed.fail", err=str(e)[:200], model=EMBEDDING_MODEL)
        return None


# ─────────────────────────────────────────────────────────────────
# Search
# ─────────────────────────────────────────────────────────────────
async def search_episodes(
    *,
    query_text: str,
    user_id: str | None = None,
    top_k: int = 3,
    only_success: bool = True,
    collection: str | None = None,
) -> list[EpisodePayload]:
    """召回 top-K 相似历史任务。

    返回:[] 若任意失败(无向量 / 服务挂 / collection 不存在)。

    设计:**永不抛**。调用方(episode_retrieval)拿到空就走 stub 逻辑。
    """
    coll = collection or WORKFLOW_TRACES_COLLECTION

    vector = await embed_text(query_text)
    if vector is None:
        log.debug("qdrant.search.no_vector", reason="embed_failed_or_mock")
        return []

    uid = str(user_id or "").strip()
    if not uid:
        log.warning("qdrant.search.skipped_missing_user_id")
        return []

    body: dict[str, Any] = {
        "vector": vector,
        "limit": max(1, min(int(top_k), 50)),
        "with_payload": True,
    }
    must: list[dict[str, Any]] = []
    must.append({"key": "user_id", "match": {"value": uid}})
    if only_success:
        must.append({"key": "outcome", "match": {"value": "success"}})
    if must:
        body["filter"] = {"must": must}

    try:
        client = _get_client()
        resp = await client.post(f"/collections/{coll}/points/search", json=body)
        if resp.status_code == 404:
            log.warning("qdrant.search.no_collection", collection=coll)
            return []
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("qdrant.search.fail", err=str(e)[:200], collection=coll)
        return []

    hits = data.get("result") or []
    if not isinstance(hits, list):
        return []
    out: list[EpisodePayload] = []
    for h in hits:
        if not isinstance(h, dict):
            continue
        try:
            out.append(EpisodePayload.from_qdrant_hit(h))
        except Exception as e:
            log.debug("qdrant.search.bad_hit", err=str(e)[:100])
            continue
    return out


# ─────────────────────────────────────────────────────────────────
# Health(可观测性 / 健康检查)
# ─────────────────────────────────────────────────────────────────
async def healthcheck() -> bool:
    """快速判断 Qdrant 是否可达 — 不抛,只返回 bool。"""
    try:
        client = _get_client()
        resp = await client.get("/collections", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────
def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
