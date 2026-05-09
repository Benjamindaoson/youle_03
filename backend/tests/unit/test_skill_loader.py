"""Skill 加载器:从 skills/playbooks/*.yaml 真实读取(铁律 9 契约)。"""

from __future__ import annotations

from app.services.skill_loader import list_available_skills, load_skill_by_id


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
