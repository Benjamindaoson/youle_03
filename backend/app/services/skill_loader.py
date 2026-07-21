"""Skill YAML 加载器(Sprint 4 用)。

铁律 9:Skill YAML 是契约;启动时把 skills/playbooks 下的 yaml load 到 DB(idempotent upsert)。
也提供 by skill_id 直接读 yaml 文件的快捷方式(测试 / dev)。

约定路径(相对 skills 根目录):
  - ``playbooks/{skill_id}.yaml`` （推荐）
  - 根目录 ``{skill_id}.yaml``（兼容迁移期）
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill import Skill

# 项目内 skills 目录(相对于本文件;运行容器里也挂相同位置)
SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
_PLAYBOOKS_SUBDIR = Path(os.getenv("SKILLS_PLAYBOOKS_SUBDIR", "playbooks"))


def _resolve_playbook_path(skill_id: str) -> Path | None:
    """返回存在的 YAML 路径;先看 playbooks/,再看根目录。"""
    stems = [f"{skill_id}.yaml", f"{skill_id}.yml"]
    for base in (SKILLS_DIR / _PLAYBOOKS_SUBDIR, SKILLS_DIR):
        if not base.is_dir():
            continue
        for name in stems:
            p = base / name
            if p.is_file():
                return p
    return None


@lru_cache(maxsize=64)
def load_skill_by_id(skill_id: str) -> dict[str, Any]:
    """读取 Playbook YAML(失败抛 KeyError)。"""
    path = _resolve_playbook_path(skill_id)
    if path is None:
        hints = SKILLS_DIR / _PLAYBOOKS_SUBDIR / f"{skill_id}.yaml"
        raise KeyError(f"skill {skill_id} not found (tried playbooks + skills root): {hints}")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_available_skills() -> list[str]:
    ids: set[str] = set()
    for base in (SKILLS_DIR / _PLAYBOOKS_SUBDIR, SKILLS_DIR):
        if not base.is_dir():
            continue
        for p in base.glob("*.yaml"):
            if p.is_file():
                ids.add(p.stem)
        for p in base.glob("*.yml"):
            if p.is_file():
                ids.add(p.stem)
    return sorted(ids)


def canonical_skill_rows() -> list[dict[str, Any]]:
    """Convert every validated playbook into the canonical database shape."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for skill_id in list_available_skills():
        path = _resolve_playbook_path(skill_id)
        if path is None:
            continue
        raw = load_skill_by_id(skill_id)
        if not isinstance(raw, dict) or raw.get("skill_id") != skill_id:
            raise ValueError(f"invalid Skill contract: {path}")
        required = ("name", "version", "workflow")
        missing = [key for key in required if not raw.get(key)]
        if missing:
            raise ValueError(f"Skill {skill_id} missing: {', '.join(missing)}")
        if skill_id in seen:
            raise ValueError(f"duplicate Skill id: {skill_id}")
        seen.add(skill_id)
        rows.append(
            {
                "skill_id": skill_id,
                "name": str(raw["name"]),
                "description": str(raw.get("description") or "") or None,
                "domain": str(raw.get("domain") or "") or None,
                "scenario": str(raw.get("scenario") or "") or None,
                "version": str(raw["version"]),
                "creator_type": str(
                    raw.get("creator_type") or raw.get("creator") or "platform"
                ),
                "visibility": str(raw.get("visibility") or "public"),
                "keywords": [str(value) for value in raw.get("keywords") or []],
                "anti_signals": [
                    str(value) for value in raw.get("anti_signals") or []
                ],
                "yaml_content": path.read_text(encoding="utf-8"),
                "inputs_schema": raw.get("inputs_schema") or [],
                "workflow_steps": raw.get("workflow") or [],
                "status": "published",
            }
        )
    if not rows:
        raise ValueError(f"no canonical Skill playbooks found under {SKILLS_DIR}")
    return rows


async def sync_builtin_skills(session: AsyncSession) -> int:
    """Idempotently seed/update canonical YAML Skills after migrations."""
    rows = canonical_skill_rows()
    statement = pg_insert(Skill).values(rows)
    mutable_columns = (
        "name",
        "description",
        "domain",
        "scenario",
        "version",
        "creator_type",
        "visibility",
        "keywords",
        "anti_signals",
        "yaml_content",
        "inputs_schema",
        "workflow_steps",
        "status",
    )
    statement = statement.on_conflict_do_update(
        index_elements=["skill_id"],
        set_={name: getattr(statement.excluded, name) for name in mutable_columns},
    )
    await session.execute(statement)
    await session.commit()
    return len(rows)
