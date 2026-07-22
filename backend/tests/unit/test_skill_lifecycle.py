from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.api.skills import (
    _canonical_skill_metadata,
    _execution_skill_filters,
    _skill_lifecycle,
    _skill_search_clause,
    disable_skill,
    enable_skill,
    install_skill,
)
from app.models.skill import Skill, UserSkillVisibility


def _skill(*, built_in: bool = False, skill_id: str = "market_skill") -> Skill:
    return Skill(
        id=uuid4(),
        skill_id=skill_id,
        name="短视频内容制作" if skill_id == "short_video" else "市场技能",
        description="生成内容",
        version="1.0",
        creator_type="platform" if built_in else "user",
        visibility="public",
        keywords=["短视频"],
        yaml_content="skill_id: market_skill",
        status="published",
    )


def _visibility(skill: Skill, relationship: str) -> UserSkillVisibility:
    return UserSkillVisibility(
        user_id=uuid4(), skill_id=skill.id, relationship=relationship
    )


@pytest.mark.parametrize(
    ("built_in", "relationship", "state", "installed", "enabled"),
    [
        (True, None, "built_in", True, True),
        (False, None, "uninstalled", False, False),
        (False, "installed_enabled", "installed_enabled", True, True),
        (False, "installed_disabled", "installed_disabled", True, False),
        (True, "installed_disabled", "installed_disabled", True, False),
    ],
)
def test_skill_lifecycle_states(
    built_in: bool,
    relationship: str | None,
    state: str,
    installed: bool,
    enabled: bool,
) -> None:
    skill = _skill(built_in=built_in)
    row = _visibility(skill, relationship) if relationship else None

    lifecycle = _skill_lifecycle(skill, row)

    assert lifecycle == {
        "lifecycle": state,
        "built_in": built_in,
        "installed": installed,
        "enabled": enabled,
        "subscribed": installed,
    }


def test_skill_search_matches_name_description_id_and_keywords() -> None:
    statement = select(Skill).where(_skill_search_clause("短视频"))
    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "skills.name ILIKE" in sql
    assert "skills.description ILIKE" in sql
    assert "skills.skill_id ILIKE" in sql
    assert "array_to_string" in sql


def test_detail_metadata_comes_from_canonical_yaml_without_prompt_bodies() -> None:
    metadata = _canonical_skill_metadata("short_video")

    assert metadata["validated"] is True
    assert metadata["version"] == "1.0"
    assert "agent_1" in metadata["required_agents"]
    assert "mcp://search/web_search" in metadata["required_mcp_tools"]
    assert "mcp:search" in metadata["permissions"]
    assert "prompt_template" not in str(metadata)
    assert "yaml_definition" not in metadata


def test_unknown_marketplace_skill_is_displayable_but_not_validated() -> None:
    metadata = _canonical_skill_metadata("not_in_canonical_playbooks")

    assert metadata == {
        "validated": False,
        "inputs_schema": [],
        "workflow_summary": [],
        "required_agents": [],
        "required_mcp_tools": [],
        "permissions": [],
    }


class _LifecycleSession:
    def __init__(
        self, skill: Skill, visibility: UserSkillVisibility | None = None
    ) -> None:
        self.skill = skill
        self.visibility = visibility
        self.statements: list[Any] = []
        self.commits = 0

    async def get(self, model: Any, _key: Any) -> Any:
        if model is Skill:
            return self.skill
        if model is UserSkillVisibility:
            return self.visibility
        return None

    async def execute(self, statement: Any) -> None:
        self.statements.append(statement)

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_install_is_idempotent_and_enables_skill() -> None:
    skill = _skill()
    session = _LifecycleSession(skill)
    user_id = uuid4()

    first = await install_skill(skill.id, user_id, session)  # type: ignore[arg-type]
    second = await install_skill(skill.id, user_id, session)  # type: ignore[arg-type]
    sql = str(session.statements[0].compile(dialect=postgresql.dialect()))

    assert first == second == {
        "skill_id": str(skill.id),
        "status": "installed_enabled",
    }
    assert "ON CONFLICT (user_id, skill_id) DO UPDATE" in sql
    assert session.commits == 2


@pytest.mark.asyncio
async def test_enable_and_disable_preserve_installation() -> None:
    skill = _skill()
    row = _visibility(skill, "installed_enabled")
    session = _LifecycleSession(skill, row)

    disabled = await disable_skill(skill.id, row.user_id, session)  # type: ignore[arg-type]
    enabled = await enable_skill(skill.id, row.user_id, session)  # type: ignore[arg-type]

    assert disabled["status"] == "installed_disabled"
    assert enabled["status"] == "installed_enabled"
    assert len(session.statements) == 2


def test_execution_filter_excludes_disabled_and_unvalidated_skills() -> None:
    filters = _execution_skill_filters(uuid4())
    sql = str(
        select(Skill).where(*filters).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )

    assert "installed_disabled" in sql
    assert "installed_enabled" in sql
    assert "skills.skill_id IN" in sql
