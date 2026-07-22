"""鉴权:短信验证码 + JWT。

dev 模式(SMS_DEV_MODE=True)直接 console.log 验证码,不发真短信。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models.user import User
from app.rate_limit import limiter
from app.services.avatar import ensure_default_avatar_style
from app.services.otp import consume_sms_otp, issue_sms_otp

router = APIRouter()
log = structlog.get_logger(__name__)


def _create_token(user_id: UUID) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(UTC) + timedelta(hours=settings.JWT_EXPIRE_HOURS),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> UUID:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token 无效") from e


async def get_current_user_id(authorization: str | None = Header(default=None)) -> UUID:
    """FastAPI dependency:从 `Authorization: Bearer <jwt>` 解出 user_id。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "缺少 Authorization 头")
    return decode_token(authorization.split(None, 1)[1].strip())


class SmsSendRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=20)


class SmsLoginRequest(BaseModel):
    phone: str
    code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str


class MeResponse(BaseModel):
    id: str
    phone: str
    nickname: str


_LOCAL_GUEST_PHONE = "local-guest"
_LOCAL_GUEST_NICKNAME = "本地访客"


@router.post("/sms/send", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("12/minute")
async def sms_send(request: Request, req: SmsSendRequest) -> None:
    from app.exceptions import SmsError

    try:
        await issue_sms_otp(req.phone)
    except SmsError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, e.message_zh) from e


@router.post("/login", response_model=TokenResponse)
@limiter.limit("30/minute")
async def login(
    request: Request,
    req: SmsLoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    if not await consume_sms_otp(req.phone, req.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "验证码错误或已过期")

    user = (await session.execute(select(User).where(User.phone == req.phone))).scalar_one_or_none()
    if user is None:
        user = User(phone=req.phone, nickname=f"用户{req.phone[-4:]}")
        ensure_default_avatar_style(user)
        session.add(user)
        await session.flush()
    else:
        ensure_default_avatar_style(user)
    user.last_login_at = datetime.now(UTC)
    await session.commit()

    token = _create_token(user.id)
    return TokenResponse(access_token=token, user_id=str(user.id))


@router.post("/local-guest", response_model=TokenResponse)
async def local_guest_login(
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Create a reusable local-only identity for the core demo."""
    if not settings.is_dev or not settings.LOCAL_GUEST_ACCESS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "本地访客访问未启用")

    user = (
        await session.execute(select(User).where(User.phone == _LOCAL_GUEST_PHONE))
    ).scalar_one_or_none()
    if user is None:
        user = User(phone=_LOCAL_GUEST_PHONE, nickname=_LOCAL_GUEST_NICKNAME)
        ensure_default_avatar_style(user)
        session.add(user)
        await session.flush()
    else:
        ensure_default_avatar_style(user)
    user.last_login_at = datetime.now(UTC)
    await session.commit()

    return TokenResponse(access_token=_create_token(user.id), user_id=str(user.id))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(user_id: UUID = Depends(get_current_user_id)) -> TokenResponse:
    return TokenResponse(access_token=_create_token(user_id), user_id=str(user_id))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout() -> None:
    return None


@router.get("/me", response_model=MeResponse)
async def me(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    return MeResponse(id=str(user.id), phone=user.phone, nickname=user.nickname or "")


# ── 工具函数已移至模块顶部(_create_token / decode_token / get_current_user_id)
