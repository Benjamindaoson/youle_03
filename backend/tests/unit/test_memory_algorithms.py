"""记忆模块确定性算法单测(无 DB)。"""
from __future__ import annotations

from uuid import uuid4

from app.models.task import Task
from app.services.memory.algorithms.artifact_profile import derive_artifact_profile
from app.services.memory.algorithms.recall_keywords import rank_artifacts_keyword
from app.services.memory.algorithms.rolling_summary import merge_rolling_summary
from app.services.memory.algorithms.task_card import build_task_memory_card, format_task_card_log_line


def test_merge_rolling_summary_appends() -> None:
    o = merge_rolling_summary("line1", "line2")
    assert "line1" in o and "line2" in o


def test_merge_rolling_summary_respects_max_chars() -> None:
    long = "a" * 100
    out = merge_rolling_summary(None, long, max_chars=50)
    assert len(out) <= 50


def test_derive_artifact_profile_uses_metadata_title() -> None:
    t, s, tags = derive_artifact_profile(
        artifact_type="image",
        reference="oss://b/k.png",
        metadata={"title": "主图", "description": "双十一主题"},
    )
    assert t == "主图"
    assert "双十一" in s
    assert "image" in tags


def test_task_memory_card_completed() -> None:
    tid = uuid4()
    cid = uuid4()
    uid = uuid4()
    task = Task(
        id=tid,
        user_id=uid,
        conversation_id=cid,
        status="completed",
        collected_fields={"年份": 2026},
        progress={"current": 2, "total": 2},
    )
    state = {
        "final_status": "completed",
        "step_results": {
            "a": {"status": "completed"},
            "b": {"status": "completed"},
        },
        "primary_artifact_ref": "oss://x",
    }
    card = build_task_memory_card(task=task, state=state)
    assert card["final_status"] == "completed"
    assert "one_liner" in card
    assert "oss://x" == card["primary_artifact_ref"]
    line = format_task_card_log_line(card)
    assert "completed" in line


def test_keyword_recall_orders() -> None:
    rows = [
        ("id1", "foo", " unrelated", "text", "r1", []),
        ("id2", "bar海报", "双十一 海报 设计", "image", "r2", ["促销"]),
    ]
    top = rank_artifacts_keyword("双十一 海报", rows)
    assert len(top) >= 1
    assert top[0].artifact_id == "id2"
