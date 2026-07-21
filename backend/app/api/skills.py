"""Skill marketplace, canonical metadata, and per-user lifecycle APIs."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id
from app.db import get_session
from app.models.skill import Skill, UserSkillVisibility
from app.services.skill_lifecycle import (
    INSTALLED_DISABLED,
    INSTALLED_ENABLED,
    _canonical_skill_metadata,
    _skill_lifecycle,
    _skill_search_clause,
)
from app.services.skill_lifecycle import (
    _execution_skill_filters as _execution_skill_filters,
)

router = APIRouter()


class SkillCard(BaseModel):
    id: UUID
    skill_id: str
    name: str
    description: str | None = None
    domain: str | None = None
    scenario: str | None = None
    version: str
    creator_type: str
    visibility: str
    keywords: list[str] = Field(default_factory=list)
    lifecycle: str
    built_in: bool
    installed: bool
    enabled: bool
    subscribed: bool


class SkillDetail(SkillCard):
    validated: bool
    inputs_schema: list[dict[str, Any]] = Field(default_factory=list)
    workflow_summary: list[dict[str, Any]] = Field(default_factory=list)
    required_agents: list[str] = Field(default_factory=list)
    required_mcp_tools: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


def _card(skill: Skill, row: UserSkillVisibility | None) -> dict[str, Any]:
    return {
        "id": skill.id,
        "skill_id": skill.skill_id,
        "name": skill.name,
        "description": skill.description,
        "domain": skill.domain,
        "scenario": skill.scenario,
        "version": skill.version,
        "creator_type": skill.creator_type,
        "visibility": skill.visibility,
        "keywords": list(skill.keywords or []),
        **_skill_lifecycle(skill, row),
    }


async def _published_skills(
    session: AsyncSession, *, query: str | None = None
) -> list[Skill]:
    statement = select(Skill).where(
        Skill.status == "published", Skill.visibility == "public"
    )
    if query and query.strip():
        statement = statement.where(_skill_search_clause(query))
    return list((await session.execute(statement)).scalars().all())


async def _visibility_by_skill(
    session: AsyncSession, user_id: UUID
) -> dict[UUID, UserSkillVisibility]:
    rows = (
        await session.execute(
            select(UserSkillVisibility).where(
                UserSkillVisibility.user_id == user_id
            )
        )
    ).scalars().all()
    return {row.skill_id: row for row in rows}


@router.get("/skills", response_model=list[SkillCard])
async def list_skills(
    domain: str | None = None,
    scenario: str | None = None,
    q: str | None = None,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    skills = await _published_skills(session, query=q)
    if domain:
        skills = [skill for skill in skills if skill.domain == domain]
    if scenario:
        skills = [skill for skill in skills if skill.scenario == scenario]
    visibility = await _visibility_by_skill(session, user_id)
    return [_card(skill, visibility.get(skill.id)) for skill in skills]


@router.get("/skills/mine", response_model=list[SkillCard])
async def my_skills(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    skills = await _published_skills(session)
    visibility = await _visibility_by_skill(session, user_id)
    cards = [_card(skill, visibility.get(skill.id)) for skill in skills]
    return [card for card in cards if card["installed"]]


@router.get("/skills/{skill_id}", response_model=SkillDetail)
async def skill_detail(
    skill_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    skill = await session.get(Skill, skill_id)
    if skill is None or skill.status != "published":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skill 不存在或未发布")
    row = await session.get(UserSkillVisibility, (user_id, skill_id))
    return {**_card(skill, row), **_canonical_skill_metadata(skill.skill_id)}


def _lifecycle_upsert(
    *, user_id: UUID, skill_id: UUID, relationship: str
) -> Any:
    return (
        pg_insert(UserSkillVisibility)
        .values(
            user_id=user_id,
            skill_id=skill_id,
            relationship=relationship,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "skill_id"],
            set_={"relationship": relationship, "updated_at": func.now()},
        )
    )


async def _require_skill(session: AsyncSession, skill_id: UUID) -> Skill:
    skill = await session.get(Skill, skill_id)
    if skill is None or skill.status != "published":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skill 不存在或未发布")
    return skill


async def _set_lifecycle(
    session: AsyncSession,
    *,
    user_id: UUID,
    skill_id: UUID,
    relationship: str,
) -> dict[str, str]:
    await session.execute(
        _lifecycle_upsert(
            user_id=user_id, skill_id=skill_id, relationship=relationship
        )
    )
    await session.commit()
    return {"skill_id": str(skill_id), "status": relationship}


@router.post("/skills/{skill_id}/install")
async def install_skill(
    skill_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    await _require_skill(session, skill_id)
    return await _set_lifecycle(
        session,
        user_id=user_id,
        skill_id=skill_id,
        relationship=INSTALLED_ENABLED,
    )


@router.post("/skills/{skill_id}/enable")
async def enable_skill(
    skill_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    skill = await _require_skill(session, skill_id)
    row = await session.get(UserSkillVisibility, (user_id, skill_id))
    if row is None and skill.creator_type != "platform":
        raise HTTPException(status.HTTP_409_CONFLICT, "Skill 尚未安装")
    return await _set_lifecycle(
        session,
        user_id=user_id,
        skill_id=skill_id,
        relationship=INSTALLED_ENABLED,
    )


@router.post("/skills/{skill_id}/disable")
async def disable_skill(
    skill_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    skill = await _require_skill(session, skill_id)
    row = await session.get(UserSkillVisibility, (user_id, skill_id))
    if row is None and skill.creator_type != "platform":
        raise HTTPException(status.HTTP_409_CONFLICT, "Skill 尚未安装")
    return await _set_lifecycle(
        session,
        user_id=user_id,
        skill_id=skill_id,
        relationship=INSTALLED_DISABLED,
    )


@router.post("/skills/{skill_id}/subscribe")
async def subscribe(
    skill_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    return await install_skill(skill_id, user_id, session)


@router.delete("/skills/{skill_id}/subscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(
    skill_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> None:
    row = await session.get(UserSkillVisibility, (user_id, skill_id))
    if row is not None:
        await session.delete(row)
        await session.commit()
