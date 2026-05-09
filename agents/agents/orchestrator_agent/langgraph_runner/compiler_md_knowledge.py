"""Playbook YAML 顶层的 md_knowledge_refs → 运行时 MD Skill 正文注入。

ADR-022: YAML 是可执行 DAG; SKILL_*.md 是知识包。本模块在 compile 时解析 refs,
由各 step 节点写入 inputs["_md_skill_knowledge"] / 与 _prompt 拼接。"""
from __future__ import annotations

import os
from typing import Any

import structlog

from agents._common.skill_registry import SkillRegistry, get_default_registry

log = structlog.get_logger(__name__)


def resolve_md_knowledge_prefix(
    skill_yaml: dict[str, Any],
    *,
    registry: SkillRegistry | None = None,
) -> str:
    """合并 skill_yaml[\"md_knowledge_refs\"] 指向的 MD Skill body(按需读盘)。

    总字符上限由 SKILL_MD_INJECT_MAX_CHARS 控制(默认 14000),避免巨量 token。
    """
    raw = skill_yaml.get("md_knowledge_refs") or skill_yaml.get("md_skill_refs")
    if isinstance(raw, str):
        refs = [raw]
    elif isinstance(raw, list):
        refs = [str(x).strip() for x in raw if str(x).strip()]
    else:
        refs = []

    if not refs:
        return ""

    cap = max(2048, int(os.getenv("SKILL_MD_INJECT_MAX_CHARS", "14000")))
    reg = registry or get_default_registry()
    chunks: list[str] = []
    used = 0

    for sid in refs:
        md = reg.find_md(sid)
        if md is None:
            log.warning(
                "lg.md_knowledge_missing",
                skill_yaml_id=skill_yaml.get("skill_id"),
                md_skill_ref=sid,
            )
            continue
        body = md.load_body().strip()
        if not body:
            continue
        if used + len(body) > cap:
            body = body[: max(0, cap - used)].rstrip() + "\n…(truncate)"
            chunks.append(f"### {sid}\n{body}")
            break
        chunks.append(f"### {sid}\n{body}")
        used += len(body) + len(sid) + 12

    return "\n\n".join(chunks).strip()
