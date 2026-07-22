"""Skill 统一注册表(ADR-022)。

# 角色
扫一个目录,把 **MD Skill(知识)** 和 **YAML Playbook(产线)** 同时索引。
Planner 拿到这份注册表后,在产 Plan 时:
  - 看到匹配场景的 MD Skill → 把 description / when_to_use / body 注入 step.prompt_template
  - 看到完全匹配的 Playbook → 在 rationale 里说明可调,但仍按 Plan schema 重新拆步

# 目录布局
- `skills/playbooks/*.yaml`: YAML 产线(优先索引)
- `skills/md_skills/*.md`: MD 知识包(优先索引)
- 仍兼容根目录平铺的旧文件

# 设计原则
1. **单源发现**:扫上述目录,不需要手写注册表
2. **轻量索引常驻 + body 按需**:符合 Anthropic progressive disclosure
3. **YAML 不解析全文**:只读必要 skill_id / name / description / scenario,完整结构由
   `agents.orchestrator_agent.task_compiler.compile_to_dag` 在执行时按需 load
4. **graceful**:目录不存在 / 单文件解析失败 → 跳过该文件 + 警告,不抛
5. **进程级单例 + 失效**:`get_default_registry()` 缓存;改文件后调 `clear()` 重新扫

仓库默认根:`agents/skills`。可用环境变量 **`SKILLS_DIR`** 覆盖根路径;
**`SKILLS_PLAYBOOKS_SUBDIR`** / **`SKILLS_MD_SUBDIR`** 可改子目录名。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
import yaml

from agents._common.skill_loader import (
    MDSkill,
    SkillLoadError,
    parse_md_skill,
)

log = structlog.get_logger(__name__)

_PLAYBOOKS_SUBDIR = os.getenv("SKILLS_PLAYBOOKS_SUBDIR", "playbooks")
_MD_SKILLS_SUBDIR = os.getenv("SKILLS_MD_SUBDIR", "md_skills")


def _default_skills_dir() -> Path:
    """SKILLS_DIR 环境变量优先;否则按本仓库布局猜 agents/skills/。"""
    env = os.getenv("SKILLS_DIR")
    if env:
        return Path(env).expanduser().resolve()
    # __file__ = .../agents/agents/_common/skill_registry.py
    # parents[2] = .../agents/(包根)
    return Path(__file__).resolve().parents[2] / "skills"


@dataclass
class PlaybookIndex:
    """YAML Playbook 的轻量索引项 — 不缓存 workflow 全文。"""

    skill_id: str
    name: str
    description: str
    domain: str | None
    scenario: str | None
    visibility: str | None
    keywords: list[str]
    source_path: Path
    raw_meta: dict[str, Any] = field(default_factory=dict)

    def summary_block(self) -> str:
        kw = ",".join(self.keywords[:5]) if self.keywords else ""
        kw_part = f" [{kw}]" if kw else ""
        desc = (self.description or "").strip().replace("\n", " ")[:160]
        return f"- {self.skill_id} ({self.name}){kw_part}: {desc}"

    def to_planner_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "domain": self.domain,
            "scenario": self.scenario,
            "keywords": list(self.keywords),
            "kind": "playbook",
        }


# ─────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────
class SkillRegistry:
    """目录级 Skill / Playbook 索引。

    用法:
        reg = SkillRegistry.from_directory(Path("agents/skills"))
        for s in reg.list_md_skills(): ...
        s = reg.find_md("xhs-note-creator")  # 命中 md_skills/SKILL_xhs-note-creator.md
        pb = reg.find_playbook("short_video")
        snapshot = reg.summary_for_planner()  # 给 planner_agent.make_plan 用
    """

    def __init__(self) -> None:
        self._md: dict[str, MDSkill] = {}
        self._playbooks: dict[str, PlaybookIndex] = {}
        self._scanned_dir: Path | None = None

    # ─── 工厂 ───
    @classmethod
    def from_directory(cls, directory: Path | str) -> "SkillRegistry":
        reg = cls()
        reg.rescan(Path(directory))
        return reg

    # ─── 扫描 ───
    def rescan(self, directory: Path) -> None:
        directory = directory.expanduser().resolve()
        self._scanned_dir = directory
        self._md.clear()
        self._playbooks.clear()

        if not directory.exists() or not directory.is_dir():
            log.warning("skill_registry.dir_missing", dir=str(directory))
            return

        for p in self._iter_playbook_files(directory):
            self._load_playbook(p)

        for p in self._iter_md_skill_files(directory):
            self._load_md(p)

        log.info(
            "skill_registry.scanned",
            dir=str(directory),
            md_count=len(self._md),
            playbook_count=len(self._playbooks),
        )

    def _iter_playbook_files(self, skills_root: Path):
        """YAML:优先 `playbooks/`,再扫根目录(兼容旧布局)。同 skill_id 以先出现的为准。"""
        roots = []
        pb = skills_root / _PLAYBOOKS_SUBDIR
        if pb.is_dir():
            roots.append(pb)
        roots.append(skills_root)
        seen_resolved: set[str] = set()
        for base in roots:
            for p in sorted(base.glob("*.yml")) + sorted(base.glob("*.yaml")):
                if not p.is_file():
                    continue
                key = str(p.resolve())
                if key in seen_resolved:
                    continue
                seen_resolved.add(key)
                yield p

    def _iter_md_skill_files(self, skills_root: Path):
        """MD:优先 `md_skills/` 再根目录。跳过 README.md。"""
        roots = []
        md_dir = skills_root / _MD_SKILLS_SUBDIR
        if md_dir.is_dir():
            roots.append(md_dir)
        roots.append(skills_root)
        seen_resolved: set[str] = set()
        for base in roots:
            for p in sorted(base.glob("*.md")):
                if not p.is_file():
                    continue
                if p.name.lower() == "readme.md":
                    continue
                key = str(p.resolve())
                if key in seen_resolved:
                    continue
                seen_resolved.add(key)
                yield p

    def _load_md(self, path: Path) -> None:
        try:
            skill = parse_md_skill(path)
        except SkillLoadError as e:
            log.warning("skill_registry.md_invalid", path=str(path), err=str(e)[:200])
            return
        if skill.skill_id in self._md:
            log.warning(
                "skill_registry.md_collision",
                skill_id=skill.skill_id,
                kept=str(self._md[skill.skill_id].source_path),
                rejected=str(path),
            )
            return
        self._md[skill.skill_id] = skill

    def _load_playbook(self, path: Path) -> None:
        try:
            raw = path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw)
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
            log.warning("skill_registry.yaml_invalid", path=str(path), err=str(e)[:200])
            return
        if not isinstance(data, dict):
            log.warning("skill_registry.yaml_not_mapping", path=str(path))
            return

        skill_id = str(data.get("skill_id") or path.stem).strip()
        if not skill_id:
            log.warning("skill_registry.playbook_no_id", path=str(path))
            return
        if skill_id in self._playbooks:
            log.warning(
                "skill_registry.playbook_collision",
                skill_id=skill_id,
                kept=str(self._playbooks[skill_id].source_path),
                rejected=str(path),
            )
            return

        self._playbooks[skill_id] = PlaybookIndex(
            skill_id=skill_id,
            name=str(data.get("name") or skill_id),
            description=str(data.get("description") or ""),
            domain=data.get("domain"),
            scenario=data.get("scenario"),
            visibility=data.get("visibility"),
            keywords=[
                str(k).strip()
                for k in (data.get("keywords") or [])
                if str(k).strip()
            ],
            source_path=path,
            raw_meta={
                "version": data.get("version"),
                "creator": data.get("creator"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
            },
        )

    # ─── 查询 ───
    def list_md_skills(self) -> list[MDSkill]:
        return list(self._md.values())

    def list_playbooks(self) -> list[PlaybookIndex]:
        return list(self._playbooks.values())

    def find_md(self, skill_id: str) -> MDSkill | None:
        return self._md.get(skill_id)

    def find_playbook(self, skill_id: str) -> PlaybookIndex | None:
        return self._playbooks.get(skill_id)

    def search_md(self, query: str, *, limit: int = 5) -> list[MDSkill]:
        """关键词在 name + description + when_to_use 上的子串匹配。

        S2 升级:换成向量召回(走 BGE-M3)。
        """
        q = (query or "").lower().strip()
        if not q:
            return []
        scored: list[tuple[int, MDSkill]] = []
        for s in self._md.values():
            blob = f"{s.name}\n{s.description}\n{s.when_to_use}".lower()
            if q in blob or q in s.skill_id:
                # 简陋打分:命中 skill_id > name > description
                score = 0
                if q in s.skill_id:
                    score += 4
                if q in s.name.lower():
                    score += 3
                if q in s.description.lower():
                    score += 2
                if q in s.when_to_use.lower():
                    score += 1
                scored.append((score, s))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:limit]]

    # ─── Planner 视图 ───
    def summary_for_planner(
        self,
        *,
        max_md: int = 30,
        max_playbooks: int = 30,
    ) -> dict[str, Any]:
        """给 planner_agent.make_plan() 喂的统一摘要。

        结构:
            {
              "md_skills": [ {skill_id, name, description, when_to_use, ...} ],
              "playbooks": [ {skill_id, name, description, domain, ...} ],
              "scanned_dir": "...",
            }
        """
        md_dicts = [s.to_planner_dict() for s in list(self._md.values())[:max_md]]
        pb_dicts = [
            p.to_planner_dict() for p in list(self._playbooks.values())[:max_playbooks]
        ]
        return {
            "md_skills": md_dicts,
            "playbooks": pb_dicts,
            "scanned_dir": str(self._scanned_dir) if self._scanned_dir else None,
        }


# ─────────────────────────────────────────────────────────────────
# 进程级单例
# ─────────────────────────────────────────────────────────────────
_default_registry: SkillRegistry | None = None


def get_default_registry() -> SkillRegistry:
    """进程级缓存的注册表(用 SKILLS_DIR 环境变量或仓库默认目录)。"""
    global _default_registry
    if _default_registry is None:
        _default_registry = SkillRegistry.from_directory(_default_skills_dir())
    return _default_registry


def clear_default_registry() -> None:
    """SKILLS_DIR 改了 / 测试要重扫 → 调这个。"""
    global _default_registry
    _default_registry = None
