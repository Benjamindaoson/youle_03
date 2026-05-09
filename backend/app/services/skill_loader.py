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
