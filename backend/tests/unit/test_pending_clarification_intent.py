from __future__ import annotations

from agents.orchestrator_agent.intent import Intent

from app.services.send_message_handlers import _coerce_pending_clarification_intent


def test_labelled_reply_is_promoted_when_clarification_is_pending() -> None:
    intent = Intent(
        intent_type="task_request",
        domain="video",
        scenario="short_video",
        entities={"主题": "城市漫游"},
        confidence=0.9,
    )

    promoted = _coerce_pending_clarification_intent(intent, pending=True)

    assert promoted.intent_type == "clarification_answer"
    assert promoted.entities == {"主题": "城市漫游"}


def test_unrelated_message_is_not_promoted_without_extracted_answer() -> None:
    intent = Intent(
        intent_type="task_request",
        domain="video",
        scenario="short_video",
        entities={},
        confidence=0.9,
    )

    assert _coerce_pending_clarification_intent(intent, pending=True) == intent
