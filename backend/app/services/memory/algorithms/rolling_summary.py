"""会话级滚动摘要 — 纯文本拼接 + 长度预算(可替换成 LLM 压缩)。"""

from __future__ import annotations


def merge_rolling_summary(
    existing: str | None,
    new_entry: str,
    *,
    max_chars: int = 8000,
    separator: str = "\n---\n",
) -> str:
    line = (new_entry or "").strip()
    if not line:
        return (existing or "").strip()
    base = (existing or "").strip()
    if not base:
        merged = line
    else:
        merged = f"{base.rstrip()}{separator}{line}"
    if len(merged) <= max_chars:
        return merged
    return merged[-max_chars:]
