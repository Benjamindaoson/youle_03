"""上传 API:走 OSS 预签名(铁律:OSS 凭证不下发客户端)。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id
from app.db import get_session
from app.models.user import User
from app.services.avatar import (
    AVATAR_PURPOSE,
    avatar_upload_prefix,
    safe_avatar_file_name,
    validate_avatar_object_key,
    validate_avatar_upload,
)
from app.services.oss import oss_service

router = APIRouter()


class SignRequest(BaseModel):
    file_name: str
    content_type: str
    purpose: str = "user_upload"  # user_upload / artifact / bgm
    size_bytes: int | None = Field(default=None, gt=0)


class SignResponse(BaseModel):
    upload_url: str
    object_key: str
    expires_in: int


class ConfirmRequest(BaseModel):
    object_key: str
    size_bytes: int = Field(gt=0)
    sha256: str | None = None


@router.post("/sign", response_model=SignResponse)
async def sign(
    body: SignRequest,
    user_id: UUID = Depends(get_current_user_id),
) -> SignResponse:
    file_name = body.file_name
    purpose = body.purpose
    if body.purpose == AVATAR_PURPOSE:
        validate_avatar_upload(content_type=body.content_type, size_bytes=body.size_bytes)
        file_name = safe_avatar_file_name(body.file_name)
        purpose = avatar_upload_prefix(user_id)

    object_key, upload_url, expires_in = await oss_service.create_presigned_put(
        file_name=file_name, content_type=body.content_type, purpose=purpose
    )
    return SignResponse(upload_url=upload_url, object_key=object_key, expires_in=expires_in)


@router.get("/avatar-url")
async def avatar_presigned_url(
    object_key: str,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """为 avatar object_key 生成限时预签名 GET URL。前端在 URL 过期前调用刷新。"""
    validate_avatar_object_key(object_key, user_id)
    url = await oss_service.get_object_url(object_key, expires_in=7 * 86400)
    return {"url": url, "expires_in": str(7 * 86400)}


@router.post("/confirm")
async def confirm(
    body: ConfirmRequest,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    if body.object_key.startswith(f"{AVATAR_PURPOSE}/"):
        validate_avatar_object_key(body.object_key, user_id)
        metadata = await oss_service.get_object_metadata(body.object_key)
        if metadata is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "上传文件不存在")
        metadata_size = metadata.get("size_bytes")
        validate_avatar_upload(
            content_type=str(metadata.get("content_type") or ""),
            size_bytes=metadata_size if isinstance(metadata_size, int) else body.size_bytes,
        )
        user = await session.get(User, user_id)
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
        # 存储 object_key 而非永久公开 URL;前端读取时通过 /upload/avatar-url 换取限时预签名 URL
        user.avatar_url = body.object_key
        await session.commit()
        await session.refresh(user)
        # 返回一个 7 天有效的预签名 GET URL 供前端立即使用
        presigned = await oss_service.get_object_url(body.object_key, expires_in=7 * 86400)
        return {"object_key": body.object_key, "status": "confirmed", "avatar_url": presigned}
    return {"object_key": body.object_key, "status": "confirmed"}
