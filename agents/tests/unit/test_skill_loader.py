"""skill_loader 单元测试(ADR-022)。

覆盖:
- 合法 frontmatter 解析(name + description)
- when_to_use / required_tools / scripts 等扩展字段
- 缺 frontmatter / 缺 name → SkillLoadError
- skill_id 派生(剥 SKILL_ 前缀,小写,连字符)
- load_body() 渐进式加载 + 缓存
- 真仓库 skills/ 下的 SKILL_*.md 全部能解析
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents._common.skill_loader import (
    MDSkill,
    SkillLoadError,
    parse_md_skill,
    parse_md_skill_from_text,
)

REPO_SKILLS_DIR = Path(__file__).resolve().parents[3] / "agents" / "skills"


def test_parse_basic_frontmatter() -> None:
    text = (
        "---\n"
        "name: demo-skill\n"
        'description: "一行说明"\n'
        "---\n"
        "\n"
        "# Body\n"
        "正文内容\n"
    )
    s = parse_md_skill_from_text(text=text, source_path=Path("/tmp/demo.md"))
    assert isinstance(s, MDSkill)
    assert s.name == "demo-skill"
    assert s.description == "一行说明"
    assert s.skill_id == "demo-skill"


def test_parse_with_extension_fields() -> None:
    text = (
        "---\n"
        "name: xhs\n"
        "description: 小红书\n"
        "when_to_use: 用户要写小红书 / 种草\n"
        "required_tools:\n"
        "  - mcp://image_tools/quality_check\n"
        "  - mcp://search/web_search\n"
        "scripts:\n"
        "  - scripts/title_check.py\n"
        "---\n"
        "body"
    )
    s = parse_md_skill_from_text(text=text)
    assert s.when_to_use == "用户要写小红书 / 种草"
    assert s.required_tools == [
        "mcp://image_tools/quality_check",
        "mcp://search/web_search",
    ]
    assert s.scripts == ["scripts/title_check.py"]


def test_missing_frontmatter_raises() -> None:
    text = "# Just markdown, no frontmatter"
    with pytest.raises(SkillLoadError):
        parse_md_skill_from_text(text=text)


def test_missing_name_raises() -> None:
    text = "---\ndescription: no name\n---\nbody"
    with pytest.raises(SkillLoadError):
        parse_md_skill_from_text(text=text)


def test_invalid_yaml_raises() -> None:
    text = "---\nname: x\n  bad: : yaml :\n---\nbody"
    with pytest.raises(SkillLoadError):
        parse_md_skill_from_text(text=text)


def test_skill_id_normalization() -> None:
    """name 里有空格 / 大小写 → skill_id 标准化。"""
    text = "---\nname: 'My Cool Skill'\ndescription: x\n---\n"
    s = parse_md_skill_from_text(text=text)
    assert s.skill_id == "my-cool-skill"


def test_skill_id_strips_skill_prefix() -> None:
    """文件名是 SKILL_xhs-note-creator.md 但 frontmatter.name=xhs-note-creator。"""
    text = "---\nname: xhs-note-creator\ndescription: x\n---\n"
    s = parse_md_skill_from_text(
        text=text, source_path=Path("/tmp/SKILL_xhs-note-creator.md")
    )
    # name 直接给的就是 xhs-note-creator,不该被 strip 掉
    assert s.skill_id == "xhs-note-creator"


def test_load_body_lazy_and_cached(tmp_path: Path) -> None:
    p = tmp_path / "demo.md"
    p.write_text(
        "---\nname: demo\ndescription: x\n---\n# Body\nhello",
        encoding="utf-8",
    )
    s = parse_md_skill(p)
    # body 还没读
    assert s._body_cache is None
    body1 = s.load_body()
    assert "# Body" in body1
    assert "hello" in body1
    # 第二次零开销 — 缓存存在
    assert s._body_cache is not None
    body2 = s.load_body()
    assert body2 is body1 or body2 == body1


def test_to_planner_dict_shape() -> None:
    text = "---\nname: x\ndescription: d\nwhen_to_use: when\n---\n"
    s = parse_md_skill_from_text(text=text)
    d = s.to_planner_dict()
    assert d["skill_id"] == "x"
    assert d["name"] == "x"
    assert d["description"] == "d"
    assert d["when_to_use"] == "when"
    assert d["kind"] == "md_skill"


# ─── 真仓库 skills/ 兼容性 ───
def test_real_repo_skill_files_all_parse() -> None:
    """`agents/skills/SKILL*.md` 必须全部能解析,不能因为格式怪而崩。"""
    if not REPO_SKILLS_DIR.exists():
        pytest.skip(f"skills dir not present at {REPO_SKILLS_DIR}")
    md_files = list((REPO_SKILLS_DIR / "md_skills").glob("*.md"))
    if not md_files:
        md_files = list(REPO_SKILLS_DIR.glob("*.md"))
    assert md_files, "expected at least one *.md under agents/skills/md_skills/"
    failures: list[tuple[Path, str]] = []
    parsed: list[MDSkill] = []
    for p in md_files:
        try:
            parsed.append(parse_md_skill(p))
        except SkillLoadError as e:
            failures.append((p, str(e)))
    assert not failures, f"failed to parse: {failures}"
    # name + description 都要有
    for s in parsed:
        assert s.name, f"{s.source_path} has no name"
        assert s.description, f"{s.source_path} has no description"
