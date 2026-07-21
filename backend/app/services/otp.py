"""Expiring, atomically consumed SMS one-time passwords."""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from app.config import settings
from app.redis_client import get_redis

log = structlog.get_logger(__name__)

_CONSUME_IF_MATCHES = """
local value = redis.call('GET', KEYS[1])
if not value or value ~= ARGV[1] then
  return 0
end
redis.call('DEL', KEYS[1])
return 1
"""


def _key(phone: str) -> str:
    return f"sms:{phone}"


async def issue_sms_otp(
    phone: str,
    *,
    redis: Any | None = None,
    dev_mode: bool | None = None,
    deliver: Callable[[str, str], Awaitable[None]] | None = None,
) -> None:
    redis = redis or await get_redis()
    use_dev_code = settings.SMS_DEV_MODE if dev_mode is None else dev_mode
    code = "123456" if use_dev_code else f"{secrets.randbelow(1_000_000):06d}"
    await redis.setex(_key(phone), settings.SMS_OTP_TTL_SECONDS, code)

    if use_dev_code:
        log.info("sms.dev_code_issued", phone_suffix=phone[-4:], dev_mode=True)
        return

    if deliver is None:
        from app.services.sms import send_sms_code

        deliver = send_sms_code
    try:
        await deliver(phone, code)
    except Exception:
        # A slower failed delivery must not remove a newer concurrent resend.
        await redis.eval(_CONSUME_IF_MATCHES, 1, _key(phone), code)
        raise


async def consume_sms_otp(
    phone: str, code: str, *, redis: Any | None = None
) -> bool:
    redis = redis or await get_redis()
    result = await redis.eval(_CONSUME_IF_MATCHES, 1, _key(phone), code)
    return int(result) == 1
