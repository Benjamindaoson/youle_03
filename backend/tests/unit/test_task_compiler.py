"""主编排子模块 5 — 任务编排器:Skill YAML → AgentTask 列表。"""

from __future__ import annotations

from uuid import uuid4

from agents.orchestrator_agent.task_compiler import compile_task


def test_compile_short_video_skill() -> None:
    skill_yaml = {
        "skill_id": "short_video",
        "version": "1.0",
        "workflow": [
            {
                "step_id": "research",
                "agent": "agent_1",
                "task_type": "web_search",
                "timeout": 120,
                "prompt_template": "搜索 {{年份}} 年的 {{主题}} 案例",
            },
            {
                "step_id": "script",
                "agent": "agent_1",
                "task_type": "long_writing",
                "depends_on": ["research"],
                "timeout": 60,
            },
            {
                "step_id": "image_process",
                "agent": "agent_3",
                "task_type": "image_download",
                "depends_on": ["research"],
                "timeout": 120,
            },
        ],
    }
    task_id, steps, agent_tasks = compile_task(
        skill_yaml=skill_yaml,
        collected_fields={"年份": 2026, "主题": "城市漫游"},
        user_id=uuid4(),
        conversation_id=uuid4(),
    )
    assert len(steps) == 3
    assert steps[0].step_id == "research"
    assert steps[2].agent_id == "agent_3"  # ADR-001-rev:图 = Agent 3
    assert agent_tasks[0].inputs["_prompt"] == "搜索 2026 年的 城市漫游 案例"


def test_compile_preserves_upstream_step_placeholders_for_runtime() -> None:
    skill_yaml = {
        "skill_id": "deferred-output",
        "version": "1.0",
        "workflow": [
            {
                "step_id": "research",
                "agent": "agent_1",
                "task_type": "web_search",
                "prompt_template": "搜索 {{topic}}",
            },
            {
                "step_id": "write",
                "agent": "agent_1",
                "task_type": "long_writing",
                "depends_on": ["research"],
                "prompt_template": "基于 {{research.output.items[0]}} 写 {{topic}}",
            },
        ],
    }

    _, _, agent_tasks = compile_task(
        skill_yaml=skill_yaml,
        collected_fields={"topic": "Agent"},
        user_id=uuid4(),
        conversation_id=uuid4(),
    )

    assert agent_tasks[1].inputs["_prompt"] == (
        "基于 {{research.output.items[0]}} 写 Agent"
    )
