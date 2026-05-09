"""轻量关键词召回 — BM25/向量前身的确定性 baseline。"""

from __future__ import annotations

import re
from dataclasses import dataclass


def tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"[^\w\u4e00-\u9fff]+", text.lower()) if len(t) >= 2}


@dataclass(frozen=True)
class ScoredSnippet:
    artifact_id: str
    title: str | None
    summary: str | None
    type: str
    reference: str
    score: float


def keyword_recall_score(query: str, title: str | None, summary: str | None, tags: list[str]) -> float:
    q_tokens = tokenize(query)
    if not q_tokens:
        return 0.0
    corp = " ".join(
        [
            title or "",
            summary or "",
            " ".join(tags),
        ]
    ).lower()
    c_tokens = tokenize(corp)
    overlap = len(q_tokens & c_tokens)
    coverage = overlap / len(q_tokens)
    # 微弱长度惩罚,倾向有摘要的结果
    length_bonus = min(1.0, len(corp) / 800.0) * 0.1
    return coverage + length_bonus


def rank_artifacts_keyword(
    query: str,
    rows: list[tuple[str, str | None, str | None, str, str, list[str]]],
    *,
    top_k: int = 12,
) -> list[ScoredSnippet]:
    """rows: (id, title, summary, type, reference, tags)"""
    ranked: list[ScoredSnippet] = []
    for aid, title, summary, typ, ref, tags in rows:
        s = keyword_recall_score(query, title, summary, tags)
        if s <= 0:
            continue
        ranked.append(
            ScoredSnippet(
                artifact_id=aid,
                title=title,
                summary=summary,
                type=typ,
                reference=ref,
                score=s,
            )
        )
    ranked.sort(key=lambda x: x.score, reverse=True)
    return ranked[:top_k]
