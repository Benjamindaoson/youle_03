"""Canonical Skill metadata, per-user lifecycle, and execution eligibility."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import and_, exists, func, not_, or_

from app.models.skill import Skill, UserSkillVisibility
from app.services.skill_loader import list_available_skills, load_skill_by_id

INSTALLED_ENABLED = "installed_enabled"
INSTALLED_DISABLED = "installed_disabled"
_LEGACY_ENABLED = "subscribed"


def _is_built_in(skill: Skill) -> bool:
    return skill.creator_type == "platform" and skill.visibility == "public"


def _skill_lifecycle(
    skill: Skill, row: UserSkillVisibility | None
) -> dict[str, bool | str]:
    built_in = _is_built_in(skill)
    relationship = row.relationship if row is not None else None
    if relationship in {INSTALLED_ENABLED, _LEGACY_ENABLED}:
        state = INSTALLED_ENABLED
        installed = enabled = True
    elif relationship == INSTALLED_DISABLED:
        state = INSTALLED_DISABLED
        installed, enabled = True, False
    elif built_in:
        state = "built_in"
        installed = enabled = True
    else:
        state = "uninstalled"
        installed = enabled = False
    return {
        "lifecycle": state,
        "built_in": built_in,
        "installed": installed,
        "enabled": enabled,
        "subscribed": installed,
    }


def _skill_search_clause(query: str) -> Any:
    pattern = f"%{query.strip()}%"
    return or_(
        Skill.name.ilike(pattern),
        Skill.description.ilike(pattern),
        Skill.skill_id.ilike(pattern),
        func.array_to_string(Skill.keywords, " ").ilike(pattern),
    )


def _canonical_skill_metadata(skill_id: str) -> dict[str, Any]:
    empty = {
        "validated": False,
        "inputs_schema": [],
        "workflow_summary": [],
        "required_agents": [],
        "required_mcp_tools": [],
        "permissions": [],
    }
    try:
        raw = load_skill_by_id(skill_id)
    except (KeyError, OSError, ValueError, TypeError):
        return empty
    if not isinstance(raw, dict) or raw.get("skill_id") != skill_id:
        return empty

    inputs = []
    for item in raw.get("inputs_schema") or []:
        if not isinstance(item, dict):
            continue
        inputs.append(
            {
                key: item[key]
                for key in ("name", "type", "required", "default", "options")
                if key in item
            }
        )

    workflow = []
    agents: set[str] = set()
    mcp_tools: set[str] = set()
    for step in raw.get("workflow") or []:
        if not isinstance(step, dict):
            continue
        agent = step.get("agent")
        if agent:
            agents.add(str(agent))
        tools = [str(tool) for tool in step.get("mcp_tools") or []]
        mcp_tools.update(tools)
        workflow.append(
            {
                key: step[key]
                for key in ("step_id", "agent", "task_type", "depends_on", "phase")
                if key in step
            }
        )

    permissions = sorted(
        {
            f"mcp:{uri.removeprefix('mcp://').split('/', 1)[0]}"
            for uri in mcp_tools
            if uri.startswith("mcp://")
        }
    )
    return {
        "validated": True,
        "version": str(raw.get("version") or ""),
        "inputs_schema": inputs,
        "workflow_summary": workflow,
        "required_agents": sorted(agents),
        "required_mcp_tools": sorted(mcp_tools),
        "permissions": permissions,
    }


def _execution_skill_filters(user_id: UUID) -> list[Any]:
    canonical_ids = list_available_skills()
    enabled = exists().where(
        UserSkillVisibility.user_id == user_id,
        UserSkillVisibility.skill_id == Skill.id,
        UserSkillVisibility.relationship.in_([INSTALLED_ENABLED, _LEGACY_ENABLED]),
    )
    disabled = exists().where(
        UserSkillVisibility.user_id == user_id,
        UserSkillVisibility.skill_id == Skill.id,
        UserSkillVisibility.relationship == INSTALLED_DISABLED,
    )
    return [
        Skill.status == "published",
        Skill.visibility == "public",
        Skill.skill_id.in_(canonical_ids or ["__no_validated_skills__"]),
        or_(and_(Skill.creator_type == "platform", not_(disabled)), enabled),
    ]
