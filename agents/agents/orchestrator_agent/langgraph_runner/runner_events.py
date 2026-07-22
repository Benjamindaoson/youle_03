"""Pure helpers for user-facing LangGraph task event payloads."""

from __future__ import annotations

from typing import Any
from uuid import UUID


def task_event(
    *,
    event_type: object,
    task_id: UUID,
    conversation_id: UUID,
    **payload: Any,
) -> dict[str, Any]:
    return {
        "type": event_type,
        "task_id": str(task_id),
        "conversation_id": str(conversation_id),
        **payload,
    }


def progress_from_state(
    state: dict[str, Any],
    *,
    previous: dict[str, Any] | None,
) -> dict[str, int]:
    results = state.get("step_results") or {}
    completed = sum(
        1
        for result in results.values()
        if isinstance(result, dict) and result.get("status") == "completed"
    )
    previous_total = int((previous or {}).get("total") or 0)
    return {"current": completed, "total": max(previous_total, len(results))}


def primary_artifact_from_state(state: dict[str, Any]) -> dict[str, Any] | None:
    reference = state.get("primary_artifact_ref")
    if not reference:
        return None
    artifact: dict[str, Any] = {"reference": reference}
    for result in (state.get("step_results") or {}).values():
        if not isinstance(result, dict) or result.get("artifact_ref") != reference:
            continue
        if result.get("artifact_type"):
            artifact["type"] = result["artifact_type"]
        if result.get("artifact_metadata"):
            artifact["metadata"] = result["artifact_metadata"]
        break
    return artifact
