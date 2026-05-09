"""skill_registry 单元测试(ADR-022)。

覆盖:
- 扫一个临时目录,MD + YAML 双索引
- 缺失目录 → 空注册表 + 警告(不抛)
- collision → 第一个胜出
- search_md 子串打分
- summary_for_planner shape
- 真仓库 agents/skills/ 能加载
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents._common.skill_registry import (
    SkillRegistry,
    clear_default_registry,
    get_default_registry,
)

REPO_SKILLS_DIR = Path(__file__).resolve().parents[3] / "agents" / "skills"


def _write_md(d: Path, fname: str, name: str, desc: str, when: str = "") -> Path:
    p = d / fname
    when_line = f"when_to_use: {when}\n" if when else ""
    p.write_text(
        f"---\nname: {name}\ndescription: {desc}\n{when_line}---\n# Body\n",
        encoding="utf-8",
    )
    return p


def _write_yaml(d: Path, fname: str, *, skill_id: str, name: str, desc: str = "") -> Path:
    p = d / fname
    p.write_text(
        f"skill_id: {skill_id}\nname: {name}\ndescription: {desc}\n"
        "domain: video\n"
        "scenario: anti_fraud\n"
        "keywords: [反诈, 短视频]\n"
        "workflow:\n"
        "  - step_id: a\n"
        "    agent: agent_1\n"
        "    task_type: web_search\n",
        encoding="utf-8",
    )
    return p


def test_registry_discovers_md_and_yaml(tmp_path: Path) -> None:
    _write_md(tmp_path, "SKILL_demo-1.md", "demo-1", "first md")
    _write_md(tmp_path, "SKILL_demo-2.md", "demo-2", "second md", when="if X")
    _write_yaml(tmp_path, "playbook_a.yaml", skill_id="pb_a", name="Playbook A")

    reg = SkillRegistry.from_directory(tmp_path)
    assert {s.skill_id for s in reg.list_md_skills()} == {"demo-1", "demo-2"}
    assert {p.skill_id for p in reg.list_playbooks()} == {"pb_a"}


def test_registry_handles_missing_directory(tmp_path: Path) -> None:
    """目录不存在不该抛。"""
    reg = SkillRegistry.from_directory(tmp_path / "nonexistent")
    assert reg.list_md_skills() == []
    assert reg.list_playbooks() == []


def test_registry_skips_invalid_files(tmp_path: Path) -> None:
    """坏的 frontmatter / 坏的 YAML → 跳过 + 警告,不影响其他文件。"""
    _write_md(tmp_path, "ok.md", "ok-md", "valid")
    (tmp_path / "broken.md").write_text("# no frontmatter", encoding="utf-8")
    (tmp_path / "broken.yaml").write_text("skill_id: x\n  bad: : yaml", encoding="utf-8")

    reg = SkillRegistry.from_directory(tmp_path)
    ids = {s.skill_id for s in reg.list_md_skills()}
    assert "ok-md" in ids
    assert "broken" not in ids


def test_registry_collision_first_wins(tmp_path: Path) -> None:
    _write_md(tmp_path, "a_first.md", "dup", "first")
    _write_md(tmp_path, "b_second.md", "dup", "second")

    reg = SkillRegistry.from_directory(tmp_path)
    md = reg.find_md("dup")
    assert md is not None
    # sorted by filename → a_first.md 胜出
    assert md.description == "first"


def test_search_md_substring_scoring(tmp_path: Path) -> None:
    _write_md(tmp_path, "a.md", "xhs-note-creator", "小红书笔记规范")
    _write_md(tmp_path, "b.md", "seo-analyser", "SEO 分析")
    _write_md(tmp_path, "c.md", "compliance", "合规与广告法", when="包含小红书审核")

    reg = SkillRegistry.from_directory(tmp_path)
    hits = reg.search_md("小红书")
    ids = [s.skill_id for s in hits]
    # 小红书 在 xhs-note-creator 的 description 命中,在 compliance 的 when_to_use 命中
    assert "xhs-note-creator" in ids
    assert "compliance" in ids
    # description 命中分高于 when_to_use → xhs-note-creator 排前
    assert ids[0] == "xhs-note-creator"
    # SEO 没命中
    assert "seo-analyser" not in ids


def test_summary_for_planner_shape(tmp_path: Path) -> None:
    _write_md(tmp_path, "a.md", "k1", "知识 1", when="when 1")
    _write_yaml(tmp_path, "p.yaml", skill_id="pb1", name="P1", desc="产线 1")

    reg = SkillRegistry.from_directory(tmp_path)
    snap = reg.summary_for_planner()
    assert "md_skills" in snap
    assert "playbooks" in snap
    assert len(snap["md_skills"]) == 1
    assert len(snap["playbooks"]) == 1
    md = snap["md_skills"][0]
    assert md["kind"] == "md_skill"
    assert md["when_to_use"] == "when 1"
    pb = snap["playbooks"][0]
    assert pb["kind"] == "playbook"
    assert pb["domain"] == "video"


def test_default_registry_uses_skills_dir_env(tmp_path: Path, monkeypatch) -> None:
    _write_md(tmp_path, "x.md", "x", "x desc")

    monkeypatch.setenv("SKILLS_DIR", str(tmp_path))
    clear_default_registry()
    reg = get_default_registry()
    assert reg.find_md("x") is not None

    # 清理避免污染其他测试
    clear_default_registry()


# ─── 真仓库 ───
def test_real_repo_skills_load() -> None:
    if not REPO_SKILLS_DIR.exists():
        pytest.skip(f"skills dir not present at {REPO_SKILLS_DIR}")
    reg = SkillRegistry.from_directory(REPO_SKILLS_DIR)
    md = reg.list_md_skills()
    pb = reg.list_playbooks()
    assert md, "expected MD skills under agents/skills/"
    assert pb, "expected YAML playbooks under agents/skills/"
    # 关键 playbook 必须命中
    pb_ids = {p.skill_id for p in pb}
    assert "anti_fraud_video" in pb_ids
    # 关键 MD skill 必须命中
    md_ids = {m.skill_id for m in md}
    assert "xhs-note-creator" in md_ids


def test_registry_loads_from_playbooks_and_md_skills_subdirs(tmp_path: Path) -> None:
    (tmp_path / "playbooks").mkdir()
    (tmp_path / "md_skills").mkdir()
    _write_yaml(tmp_path / "playbooks", "nested.yaml", skill_id="nested_pb", name="Nested PB")
    _write_md(tmp_path / "md_skills", "k.md", "nested-md", "nested desc")

    reg = SkillRegistry.from_directory(tmp_path)
    assert reg.find_playbook("nested_pb") is not None
    assert reg.find_md("nested-md") is not None
