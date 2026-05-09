"""素材库 + 知识库 + 成果库 + 设置 API(v4 §31, §34, §39)。

- /api/materials       素材 CRUD
- /api/prompts         Prompt 收藏 CRUD
- /api/artifacts       成果库(只读 + 过滤)
- /api/settings        用户设置
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id
from app.db import get_session
from app.models.artifact import Artifact
from app.models.material import Material, PromptItem
from app.models.user import User
from app.services.avatar import ensure_default_avatar_style, validate_avatar_style

router = APIRouter()
log = structlog.get_logger(__name__)


# ──────────────────────── 素材库 ────────────────────────
class MaterialIn(BaseModel):
    name: str
    mime: str | None = None
    folder: str | None = None
    url: str | None = None
    oss_key: str | None = None
    size_bytes: int | None = None
    source: str = Field(default="upload")


class MaterialOut(BaseModel):
    id: UUID
    name: str
    mime: str | None = None
    folder: str | None = None
    url: str | None = None
    size_bytes: int | None = None
    source: str
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/materials", response_model=list[MaterialOut])
async def list_materials(
    folder: str | None = None,
    mime_prefix: str | None = Query(default=None, description="按 MIME 前缀过滤,如 image/"),
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> list[Material]:
    stmt = select(Material).where(Material.user_id == user_id).order_by(desc(Material.created_at))
    if folder:
        stmt = stmt.where(Material.folder == folder)
    if mime_prefix:
        stmt = stmt.where(Material.mime.startswith(mime_prefix))
    return list((await session.execute(stmt)).scalars().all())


@router.post("/materials", response_model=MaterialOut, status_code=status.HTTP_201_CREATED)
async def create_material(
    body: MaterialIn,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Material:
    m = Material(
        id=uuid4(),
        user_id=user_id,
        name=body.name,
        mime=body.mime,
        folder=body.folder,
        url=body.url,
        oss_key=body.oss_key,
        size_bytes=body.size_bytes,
        source=body.source,
    )
    session.add(m)
    await session.commit()
    await session.refresh(m)
    log.info("library.material.created", id=str(m.id), folder=body.folder)
    return m


@router.delete("/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_material(
    material_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> None:
    m = await session.get(Material, material_id)
    if m is None or m.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "素材不存在")
    await session.delete(m)
    await session.commit()


# ──────────────────────── 知识库(Prompt 收藏)────────────────────────
class PromptIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1)


class PromptOut(BaseModel):
    id: UUID
    name: str
    content: str
    used_count: int
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/prompts", response_model=list[PromptOut])
async def list_prompts(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> list[PromptItem]:
    stmt = (
        select(PromptItem)
        .where(PromptItem.user_id == user_id)
        .order_by(desc(PromptItem.used_count), desc(PromptItem.created_at))
    )
    return list((await session.execute(stmt)).scalars().all())


@router.post("/prompts", response_model=PromptOut, status_code=status.HTTP_201_CREATED)
async def create_prompt(
    body: PromptIn,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> PromptItem:
    p = PromptItem(id=uuid4(), user_id=user_id, name=body.name, content=body.content)
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return p


@router.delete("/prompts/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt(
    prompt_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> None:
    p = await session.get(PromptItem, prompt_id)
    if p is None or p.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "提示词不存在")
    await session.delete(p)
    await session.commit()


@router.post("/prompts/{prompt_id}/use")
async def increment_prompt_use(
    prompt_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    p = await session.get(PromptItem, prompt_id)
    if p is None or p.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "提示词不存在")
    p.used_count += 1
    await session.commit()
    return {"id": str(p.id), "used_count": p.used_count}


# ──────────────────────── 成果库(Artifact 视图)────────────────────────
class ArtifactRow(BaseModel):
    id: UUID
    source_task_id: UUID | None = None
    source_conversation_id: UUID
    source_step_id: str | None = None
    type: str
    is_final: bool
    reference: str
    title: str | None = None
    created_at: str

    model_config = {"from_attributes": True}


def _artifact_to_row(a: Artifact) -> dict[str, Any]:
    md = a.extra_metadata or {}
    return {
        "id": a.id,
        "source_task_id": a.source_task_id,
        "source_conversation_id": a.source_conversation_id,
        "source_step_id": a.source_step_id,
        "type": a.type,
        "is_final": a.is_final,
        "reference": a.reference,
        "title": md.get("title"),
        "created_at": a.created_at.isoformat() if a.created_at else "",
    }


@router.get("/artifacts", response_model=list[ArtifactRow])
async def list_artifacts(
    artifact_type: str | None = Query(default=None, description="过滤类型:text/image/video/document"),
    conversation_id: UUID | None = None,
    only_final: bool = False,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    stmt = (
        select(Artifact)
        .where(Artifact.user_id == user_id)
        .order_by(desc(Artifact.created_at))
    )
    if artifact_type:
        stmt = stmt.where(Artifact.type == artifact_type)
    if conversation_id:
        stmt = stmt.where(Artifact.source_conversation_id == conversation_id)
    if only_final:
        stmt = stmt.where(Artifact.is_final.is_(True))
    rows = (await session.execute(stmt)).scalars().all()
    return [_artifact_to_row(a) for a in rows]


# ──────────────────────── 设置 / 个人主页 ────────────────────────
class ProfileOut(BaseModel):
    id: UUID
    phone: str
    nickname: str | None = None
    avatar_url: str | None = None
    avatar_style: str | None = None
    plan: str
    created_at: datetime
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProfilePatch(BaseModel):
    nickname: str | None = None
    avatar_url: str | None = None
    avatar_style: str | None = None


@router.get("/profile/me", response_model=ProfileOut)
async def get_profile(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    if ensure_default_avatar_style(user):
        await session.commit()
        await session.refresh(user)
    return user


@router.patch("/profile/me", response_model=ProfileOut)
async def patch_profile(
    body: ProfilePatch,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    if body.nickname is not None:
        user.nickname = body.nickname
    if body.avatar_url is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "头像 URL 必须通过头像上传确认接口更新")
    if body.avatar_style is not None:
        user.avatar_style = validate_avatar_style(body.avatar_style)
    await session.commit()
    await session.refresh(user)
    return user


# ──────────────────────── 统计(个人主页用)────────────────────────
@router.get("/profile/me/stats")
async def profile_stats(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    from sqlalchemy import func as sqlfunc

    from app.models.task import Task

    artifact_count = await session.scalar(
        select(sqlfunc.count(Artifact.id)).where(Artifact.user_id == user_id)
    )
    skills_used = await session.scalar(
        select(sqlfunc.count(sqlfunc.distinct(Task.skill_id))).where(Task.user_id == user_id)
    )
    return {
        "artifacts": int(artifact_count or 0),
        "skills_used": int(skills_used or 0),
    }
