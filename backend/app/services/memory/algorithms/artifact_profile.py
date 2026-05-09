"""确定性算法:从产物元数据推导 title / summary / tags(无 LLM 亦可运行)。"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote, urlparse


def _ref_tail(reference: str, max_len: int = 64) -> str:
    ref = (reference or "").strip()
    if len(ref) <= max_len:
        return ref
    return "…" + ref[-max_len:]


def _pick_text_from_metadata(meta: dict[str, Any]) -> str:
    for key in ("description", "caption", "summary", "text_excerpt", "title"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def derive_artifact_profile(
    *,
    artifact_type: str,
    reference: str,
    metadata: dict[str, Any] | None,
) -> tuple[str, str, list[str]]:
    """返回 (title, summary, tags)。"""
    meta = metadata or {}
    title = str(meta.get("title") or "").strip()
    raw_text = _pick_text_from_metadata(meta)
    summary_source = raw_text or ""

    if not title:
        parsed = urlparse(reference)
        slug = unquote(parsed.path.rsplit("/", maxsplit=1)[-1]) if parsed.path else reference
        slug = re.sub(r"^[\s\-_]+|[\s\-_]+$", "", slug) or artifact_type
        title = f"{artifact_type}:{slug[:80]}"

    summary = (summary_source[:600] + "…") if len(summary_source) > 600 else summary_source
    if not summary:
        summary = f"产物类型 {artifact_type} — ref {_ref_tail(reference, 120)}"

    tags: list[str] = [artifact_type.lower()]
    raw_tags = meta.get("tags") or meta.get("memory_tags")
    if isinstance(raw_tags, list):
        tags.extend(str(t).strip() for t in raw_tags if str(t).strip())
    elif isinstance(raw_tags, str) and raw_tags.strip():
        tags.append(raw_tags.strip())

    # 去重保持顺序
    seen: set[str] = set()
    uniq: list[str] = []
    for t in tags:
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            uniq.append(t)
    return title, summary, uniq[:24]
