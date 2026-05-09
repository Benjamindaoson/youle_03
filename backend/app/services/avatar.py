from __future__ import annotations

import hashlib
import re
from pathlib import PurePath
from uuid import UUID

from fastapi import HTTPException, status

from app.models.user import User

AVATAR_PURPOSE = "avatar"
AVATAR_MAX_BYTES = 5 * 1024 * 1024
AVATAR_ALLOWED_CONTENT_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
AVATAR_STYLES = (
    "pixel-emerald",
    "pixel-amber",
    "pixel-violet",
    "pixel-cyan",
    "nft-rose",
    "nft-indigo",
    "nft-slate",
    "nft-gold",
)

_SAFE_FILE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def default_avatar_style(seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return AVATAR_STYLES[digest[0] % len(AVATAR_STYLES)]


def ensure_default_avatar_style(user: User) -> bool:
    if user.avatar_style:
        return False
    seed = user.phone or str(user.id)
    user.avatar_style = default_avatar_style(seed)
    return True


def validate_avatar_style(style: str) -> str:
    if style not in AVATAR_STYLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不支持的头像风格")
    return style


def validate_avatar_upload(*, content_type: str, size_bytes: int | None = None) -> None:
    if content_type not in AVATAR_ALLOWED_CONTENT_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "头像仅支持 PNG/JPEG/WebP 图片")
    if size_bytes is not None and size_bytes > AVATAR_MAX_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "头像文件不能超过 5MB")


def avatar_upload_prefix(user_id: UUID) -> str:
    return f"{AVATAR_PURPOSE}/{user_id}"


def validate_avatar_object_key(object_key: str, user_id: UUID) -> None:
    if not object_key.startswith(f"{avatar_upload_prefix(user_id)}/"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "头像文件不属于当前用户")


def safe_avatar_file_name(file_name: str) -> str:
    name = PurePath(file_name).name.strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件名不能为空")
    safe_name = _SAFE_FILE_NAME.sub("_", name)
    if safe_name in {".", ".."}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件名不合法")
    return safe_name
