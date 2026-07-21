"""Skill 加载器:从 skills/playbooks/*.yaml 真实读取(铁律 9 契约)。"""

from __future__ import annotations

from app.services.skill_loader import (
    canonical_skill_rows,
    list_available_skills,
    load_skill_by_id,
    sync_builtin_skills,
)


def test_list_includes_v1_heroes() -> None:
    skills = list_available_skills()
    assert "anti_fraud_video" in skills
    assert "ecommerce_detail_image" in skills


def test_load_anti_fraud_video_shape() -> None:
    skill = load_skill_by_id("anti_fraud_video")
    assert skill["skill_id"] == "anti_fraud_video"
    assert skill["scenario"] == "anti_fraud"

    # workflow 5 个 step,Agent 编号符合 ADR-001-rev
    workflow = skill["workflow"]
    assert len(workflow) == 5
    by_id = {s["step_id"]: s for s in workflow}
    assert by_id["research"]["agent"] == "agent_1"
    assert by_id["script"]["agent"] == "agent_1"
    assert by_id["image_process"]["agent"] == "agent_3"   # ADR-001-rev:图 = 3
    assert by_id["bgm"]["agent"] == "agent_4"             # ADR-001-rev:影音 = 4
    assert by_id["video_compose"]["agent"] == "agent_4"

    # V1 终审:无 rollback action(铁律 14)
    final = by_id["video_compose"]["hitl_gate"]
    actions = [a["action"] for a in final["actions"]]
    assert "approve" in actions
    assert "rollback" not in actions


def test_load_ecommerce_detail_image() -> None:
    skill = load_skill_by_id("ecommerce_detail_image")
    by_id = {s["step_id"]: s for s in skill["workflow"]}
    assert by_id["long_concat"]["agent"] == "agent_2"   # ADR-001-rev:文档 = 2(长图拼接)
    assert by_id["segment_images"]["agent"] == "agent_3"


def test_canonical_skill_rows_are_validated_database_records() -> None:
    rows = canonical_skill_rows()
    by_id = {row["skill_id"]: row for row in rows}

    assert set(by_id) >= {"anti_fraud_video", "ecommerce_detail_image"}
    assert by_id["anti_fraud_video"]["creator_type"] == "platform"
    assert by_id["anti_fraud_video"]["status"] == "published"
    assert by_id["anti_fraud_video"]["inputs_schema"]
    assert by_id["anti_fraud_video"]["workflow_steps"]
    assert "skill_id: anti_fraud_video" in by_id["anti_fraud_video"]["yaml_content"]


async def test_sync_builtin_skills_is_one_idempotent_upsert() -> None:
    class Session:
        def __init__(self) -> None:
            self.statements: list[object] = []
            self.commits = 0

        async def execute(self, statement: object) -> None:
            self.statements.append(statement)

        async def commit(self) -> None:
            self.commits += 1

    session = Session()
    count = await sync_builtin_skills(session)  # type: ignore[arg-type]

    assert count == len(canonical_skill_rows())
    assert len(session.statements) == 1
    assert session.commits == 1
