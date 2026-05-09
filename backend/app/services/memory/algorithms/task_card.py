"""Task 履历卡 — 从 LangGraph 收敛态 + Task ORM 抽取结构化 episodic。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.task import Task


def build_task_memory_card(*, task: Task, state: dict[str, Any]) -> dict[str, Any]:
    final = str(state.get("final_status") or "completed")
    results = state.get("step_results") or {}
    completed = 0
    failed = 0
    for r in results.values():
        if not isinstance(r, dict):
            continue
        st = r.get("status")
        if st == "completed":
            completed += 1
        elif st == "failed":
            failed += 1

    total_hint = 0
    if isinstance(task.progress, dict):
        total_hint = int(task.progress.get("total") or 0)
    total_steps = max(total_hint, len(results)) or total_hint

    primary = state.get("primary_artifact_ref")

    fields = task.collected_fields or {}
    gist_parts: list[str] = []
    if isinstance(fields, dict):
        for k in list(fields.keys())[:5]:
            val = fields[k]
            if isinstance(val, (str, int, float, bool)):
                gist_parts.append(f"{k}={val}")
    gist = ", ".join(gist_parts[:3])

    if final == "completed":
        one = f"已完成工作流({completed}/{total_steps or '?'} 步){f'; {gist}' if gist else ''}"
    elif final == "failed":
        reason = (state.get("failure_reason") or "")[:200]
        one = f"失败({failed} 步失败){f'; {reason}' if reason else ''}"
    else:
        one = f"状态 {final} — 步进 {completed}/{total_steps or '?'}"

    return {
        "version": 1,
        "task_id": str(task.id),
        "conversation_id": str(task.conversation_id),
        "final_status": final,
        "one_liner": one,
        "primary_artifact_ref": primary,
        "step_counts": {
            "completed": completed,
            "failed": failed,
            "known_total": total_steps,
        },
        "gist_fields": gist,
    }


def format_task_card_log_line(card: dict[str, Any]) -> str:
    """写入 rolling summary 的单行人类可读摘要。"""
    tid = str(card.get("task_id") or "")[:8]
    status = card.get("final_status") or "?"
    line = card.get("one_liner") or ""
    return f"[{status}] task …{tid} — {line}"
