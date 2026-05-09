"""子模块 2:Skill 匹配 — 三层检索。

L1 关键词(scenario/domain 精确匹配)
L2 TF-IDF 余弦相似度(无需外部服务,无网络开销)
L3 LLM 兜底(仅 L2 < 阈值时调用,~1% 频率)

返回 MatchResult 含 confidence(0.0-1.0)和 layer_used 字段供澄清触发判断。
"""

from __future__ import annotations

import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill import Skill

log = structlog.get_logger(__name__)

L2_ACCEPT_THRESHOLD = 0.35   # L2 score >= this → use result, skip L3
L2_REJECT_THRESHOLD = 0.10   # L2 score < this → escalate to L3
# Between 0.10 and 0.35 → L3 for reranking


@dataclass
class MatchResult:
    skill: Skill | None
    confidence: float           # 0.0-1.0
    layer_used: str             # "l1_exact"|"l1_domain"|"l2_similarity"|"l3_llm"|"none"
    candidates_count: int = 0
    needs_clarification: bool = field(init=False)

    def __post_init__(self) -> None:
        self.needs_clarification = self.skill is not None and self.confidence < 0.55


# ── tokenizer ──────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """CJK character-level + ASCII word tokenizer (no external deps)."""
    text = text.lower()
    tokens: list[str] = []
    buf = ""
    for ch in text:
        if "一" <= ch <= "鿿":
            if buf:
                tokens.extend(t for t in re.findall(r"\w+", buf) if t)
                buf = ""
            tokens.append(ch)
        elif ch.isalnum() or ch == "_":
            buf += ch
        else:
            if buf:
                tokens.extend(t for t in re.findall(r"\w+", buf) if t)
                buf = ""
    if buf:
        tokens.extend(t for t in re.findall(r"\w+", buf) if t)
    return tokens


def _cosine(tf_a: Counter, tf_b: Counter) -> float:
    """Cosine similarity between two term-frequency vectors."""
    if not tf_a or not tf_b:
        return 0.0
    dot = sum(tf_a[t] * tf_b[t] for t in tf_a if t in tf_b)
    norm_a = math.sqrt(sum(v * v for v in tf_a.values()))
    norm_b = math.sqrt(sum(v * v for v in tf_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _skill_text(skill: Skill) -> str:
    parts = [
        skill.name or "",
        skill.scenario or "",
        skill.domain or "",
        getattr(skill, "description", "") or "",
    ]
    return " ".join(p for p in parts if p)


# ── L3 LLM rerank ──────────────────────────────────────────────────────────────

async def _l3_llm_rerank(
    user_message: str,
    candidates: list[Skill],
    intent: dict[str, Any],
    *,
    memory_context: str = "",
) -> MatchResult:
    """LLM rerank via LiteLLM — only called when L2 confidence is low."""
    import json

    try:
        import httpx

        litellm_url = os.getenv("LITELLM_URL", "http://litellm-proxy:4000")
        litellm_key = os.getenv("LITELLM_API_KEY", "sk-mock-1234")
        litellm_mock = os.getenv("LITELLM_MOCK", "true").lower() == "true"

        if litellm_mock:
            # In mock mode, return best L2 match with moderate confidence
            if candidates:
                return MatchResult(
                    skill=candidates[0],
                    confidence=0.60,
                    layer_used="l3_llm",
                    candidates_count=len(candidates),
                )
            return MatchResult(skill=None, confidence=0.0, layer_used="none")

        skill_list = "\n".join(
            f"{i + 1}. {s.name}({s.scenario}): {getattr(s, 'description', '') or ''}"
            for i, s in enumerate(candidates[:5])
        )
        mem_block = ""
        if memory_context.strip():
            mem_block = f"会话记忆片段:\n{memory_context.strip()[:400]}\n\n"
        prompt = (
            f"用户消息: {user_message[:200]}\n"
            f"{mem_block}"
            f"意图: {json.dumps(intent, ensure_ascii=False)[:100]}\n\n"
            f"候选技能:\n{skill_list}\n\n"
            "选择最匹配的技能编号(1-N),或 0 表示均不匹配。"
            '以 JSON 格式回答: {"choice": N, "confidence": 0.0-1.0}'
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{litellm_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {litellm_key}"},
                json={
                    "model": "deepseek-v4-flash",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1,
                },
            )
            resp.raise_for_status()
            raw = resp.json()

        data = json.loads(raw["choices"][0]["message"]["content"])
        choice = int(data.get("choice", 0))
        confidence = float(data.get("confidence", 0.0))

        if 1 <= choice <= len(candidates):
            log.debug("skill_match.l3_hit", skill=candidates[choice - 1].name, confidence=confidence)
            return MatchResult(
                skill=candidates[choice - 1],
                confidence=round(confidence, 3),
                layer_used="l3_llm",
                candidates_count=len(candidates),
            )

    except Exception as e:
        log.warning("skill_match.l3_failed", err=str(e))

    return MatchResult(skill=None, confidence=0.0, layer_used="none", candidates_count=len(candidates))


# ── public API ─────────────────────────────────────────────────────────────────

async def match_skill(
    *,
    session: AsyncSession,
    user_message: str,
    intent: dict[str, Any],
    memory_context: str = "",
) -> Skill | None:
    """Backwards-compatible wrapper — returns Skill or None."""
    result = await match_skill_with_confidence(
        session=session,
        user_message=user_message,
        intent=intent,
        memory_context=memory_context,
    )
    return result.skill


async def match_skill_with_confidence(
    *,
    session: AsyncSession,
    user_message: str,
    intent: dict[str, Any],
    memory_context: str = "",
) -> MatchResult:
    """Full match with confidence score. Preferred for orchestrator use."""
    domain = intent.get("domain")
    scenario = intent.get("scenario")
    base_filters = [Skill.status == "published", Skill.visibility == "public"]

    # ── L1: exact scenario match ──────────────────────────────────────────────
    candidates: list[Skill] = []
    if scenario:
        rows = await session.execute(
            select(Skill).where(Skill.scenario == scenario, *base_filters)
        )
        candidates = list(rows.scalars().all())

    if len(candidates) == 1:
        log.debug("skill_match.l1_exact", scenario=scenario, skill=candidates[0].name)
        return MatchResult(skill=candidates[0], confidence=0.95, layer_used="l1_exact", candidates_count=1)

    # ── L1: domain fallback ───────────────────────────────────────────────────
    if not candidates and domain:
        rows = await session.execute(
            select(Skill).where(Skill.domain == domain, *base_filters)
        )
        candidates = list(rows.scalars().all())

    if len(candidates) == 1:
        log.debug("skill_match.l1_domain", domain=domain, skill=candidates[0].name)
        return MatchResult(skill=candidates[0], confidence=0.80, layer_used="l1_domain", candidates_count=1)

    # ── L2: TF-IDF similarity over all published skills ───────────────────────
    if not candidates:
        rows = await session.execute(select(Skill).where(*base_filters))
        candidates = list(rows.scalars().all())

    if not candidates:
        log.debug("skill_match.no_candidates", message=user_message[:50])
        return MatchResult(skill=None, confidence=0.0, layer_used="none")

    mem_tail = (memory_context or "").strip()[:800]
    query_text = " ".join(
        filter(
            None,
            [user_message, str(domain or ""), str(scenario or ""), mem_tail or None],
        )
    )
    query_tf = Counter(_tokenize(query_text))

    scored = sorted(
        ((skill, _cosine(query_tf, Counter(_tokenize(_skill_text(skill))))) for skill in candidates),
        key=lambda x: x[1],
        reverse=True,
    )
    best_skill, best_score = scored[0]

    if best_score >= L2_ACCEPT_THRESHOLD:
        log.debug("skill_match.l2_hit", skill=best_skill.name, score=round(best_score, 3))
        return MatchResult(
            skill=best_skill,
            confidence=round(best_score, 3),
            layer_used="l2_similarity",
            candidates_count=len(candidates),
        )

    # ── L3: LLM rerank for low-confidence cases ───────────────────────────────
    log.debug("skill_match.escalate_l3", best_score=round(best_score, 3), candidates=len(candidates))
    return await _l3_llm_rerank(
        user_message, [s for s, _ in scored[:5]], intent, memory_context=memory_context
    )
