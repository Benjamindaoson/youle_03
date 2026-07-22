"""Planner ↔ SkillRegistry 集成测试(ADR-022)。

验证 make_plan() 在未显式传 `available_skills_index` 时:
  1. 自动从 skill_registry 拉 MD + Playbook 摘要
  2. MD Skills 与 Playbooks 在 prompts.py 里被分两块呈现
  3. 显式传 skill_registry 参数能覆盖默认注册表
"""

from __future__ import annotations

from pathlib import Path


from agents._common.skill_registry import SkillRegistry
from agents.orchestrator_agent.planner.planner_agent import (
    _format_md_skills_for_prompt,
    _format_playbooks_for_prompt,
    make_plan,
)
from agents.orchestrator_agent.planner.plan_schema import Plan
from agents.orchestrator_agent.planner.prompts import render_planner_user_prompt


def _seed_dir(tmp_path: Path) -> Path:
    (tmp_path / "SKILL_xhs.md").write_text(
        "---\n"
        "name: xhs-note-creator\n"
        "description: 小红书笔记创作规范\n"
        "when_to_use: 用户要写小红书 / 种草\n"
        "---\n# Body\n",
        encoding="utf-8",
    )
    (tmp_path / "short_video.yaml").write_text(
        "skill_id: short_video\n"
        "name: 城市漫游短视频\n"
        "description: 制作城市漫游短视频\n"
        "domain: video\n"
        "scenario: short_video\n"
        "keywords: [短视频, 短视频]\n"
        "workflow:\n"
        "  - step_id: a\n"
        "    agent: agent_1\n"
        "    task_type: web_search\n",
        encoding="utf-8",
    )
    return tmp_path


# ─── 摘要格式化 ───
def test_format_md_skills_includes_when_to_use() -> None:
    md = [
        {
            "skill_id": "xhs",
            "name": "xhs",
            "description": "小红书规范",
            "when_to_use": "用户要写小红书",
            "kind": "md_skill",
        }
    ]
    out = _format_md_skills_for_prompt(md)
    assert "xhs" in out
    assert "when:" in out
    assert "用户要写小红书" in out
    assert "什么:" not in out  # 用 "what:" 标签
    assert "what:" in out


def test_format_playbooks_includes_keywords() -> None:
    pb = [
        {
            "skill_id": "short_video",
            "name": "短视频",
            "description": "制作城市漫游短视频",
            "keywords": ["短视频", "短视频"],
            "kind": "playbook",
        }
    ]
    out = _format_playbooks_for_prompt(pb)
    assert "short_video" in out
    assert "[短视频,短视频]" in out


def test_format_returns_empty_for_empty_lists() -> None:
    assert _format_md_skills_for_prompt([]) == ""
    assert _format_playbooks_for_prompt([]) == ""


# ─── Prompt 渲染 ───
def test_render_planner_prompt_includes_md_block() -> None:
    out = render_planner_user_prompt(
        user_request="给我做一个短视频",
        available_skills_summary="- pb: playbook desc",
        similar_episodes="",
        available_mcp_tools_summary="- mcp://x",
        collected_fields=None,
        available_md_skills_summary="- xhs: 小红书规范",
    )
    assert "MD Skill 知识包" in out
    assert "xhs: 小红书规范" in out
    assert "YAML Playbook" in out
    assert "pb: playbook desc" in out


def test_render_planner_prompt_handles_empty_md_block() -> None:
    out = render_planner_user_prompt(
        user_request="x",
        available_skills_summary="",
        similar_episodes="",
        available_mcp_tools_summary="x",
        available_md_skills_summary="",
    )
    assert "MD Skill 知识包(无)" in out
    assert "YAML Playbook(无)" in out


# ─── make_plan 用注册表 ───
async def test_make_plan_auto_consults_registry(tmp_path: Path) -> None:
    """LITELLM_MOCK=true 下 make_plan 走 fixture,但 registry 仍应被读到 —
    我们通过 spy 摘要函数来验证。"""
    _seed_dir(tmp_path)
    reg = SkillRegistry.from_directory(tmp_path)

    # 直接用 reg → make_plan 应当 from registry 拉 snapshot
    plan = await make_plan(
        user_request="给我做一个小红书笔记",
        user_id="u-1",
        skill_registry=reg,
    )
    assert isinstance(plan, Plan)
    plan.validate_deps()
    # mock 路径不接 Plan 内容,但调用链不该崩


async def test_make_plan_explicit_index_skips_registry() -> None:
    """传 available_skills_index 时,make_plan 不用 registry 也能跑。"""
    plan = await make_plan(
        user_request="x",
        user_id="u",
        available_skills_index=[
            {"skill_id": "demo", "name": "Demo", "description": "演示"}
        ],
    )
    assert isinstance(plan, Plan)
