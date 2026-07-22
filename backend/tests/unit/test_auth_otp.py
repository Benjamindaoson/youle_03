from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.api import auth
from app.exceptions import SmsError
from app.services.otp import consume_sms_otp, issue_sms_otp


class _AtomicRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.ttls[key] = ttl

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)

    async def eval(self, _script: str, _keys: int, key: str, expected: str) -> int:
        async with self._lock:
            if self.values.get(key) != expected:
                return 0
            del self.values[key]
            return 1


class _Result:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value


class _UserSession:
    def __init__(self, user: Any = None) -> None:
        self.user = user
        self.executions = 0
        self.added: list[Any] = []
        self.commits = 0

    async def execute(self, _statement: Any) -> _Result:
        self.executions += 1
        return _Result(self.user)

    def add(self, user: Any) -> None:
        self.added.append(user)

    async def flush(self) -> None:
        if self.added and self.added[-1].id is None:
            self.added[-1].id = uuid4()

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_issue_sms_otp_stores_dev_code_with_ttl() -> None:
    redis = _AtomicRedis()

    await issue_sms_otp("13800138000", redis=redis, dev_mode=True)

    assert redis.values["sms:13800138000"] == "123456"
    assert redis.ttls["sms:13800138000"] == 300


@pytest.mark.asyncio
async def test_delivery_failure_removes_new_code() -> None:
    redis = _AtomicRedis()

    async def fail_delivery(_phone: str, _code: str) -> None:
        raise SmsError("provider unavailable")

    with pytest.raises(SmsError):
        await issue_sms_otp(
            "13800138000",
            redis=redis,
            dev_mode=False,
            deliver=fail_delivery,
        )

    assert "sms:13800138000" not in redis.values


@pytest.mark.asyncio
async def test_old_delivery_failure_does_not_delete_concurrent_new_code() -> None:
    redis = _AtomicRedis()

    async def fail_after_resend(_phone: str, _code: str) -> None:
        await redis.setex("sms:13800138000", 300, "654321")
        raise SmsError("provider unavailable")

    with pytest.raises(SmsError):
        await issue_sms_otp(
            "13800138000",
            redis=redis,
            dev_mode=False,
            deliver=fail_after_resend,
        )

    assert redis.values["sms:13800138000"] == "654321"


@pytest.mark.asyncio
async def test_wrong_or_expired_code_is_rejected_without_consuming_valid_code() -> None:
    redis = _AtomicRedis()
    await redis.setex("sms:13800138000", 300, "654321")

    assert not await consume_sms_otp("13800138000", "000000", redis=redis)
    assert await consume_sms_otp("13800138000", "654321", redis=redis)
    assert not await consume_sms_otp("13800138001", "654321", redis=redis)


@pytest.mark.asyncio
async def test_concurrent_otp_consumption_succeeds_exactly_once() -> None:
    redis = _AtomicRedis()
    await redis.setex("sms:13800138000", 300, "654321")

    results = await asyncio.gather(
        consume_sms_otp("13800138000", "654321", redis=redis),
        consume_sms_otp("13800138000", "654321", redis=redis),
    )

    assert sorted(results) == [False, True]


@pytest.mark.asyncio
async def test_login_consumes_code_and_returns_refreshable_jwt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _AtomicRedis()
    await redis.setex("sms:13800138000", 300, "654321")
    session = _UserSession()

    async def fake_get_redis() -> _AtomicRedis:
        return redis

    monkeypatch.setattr("app.services.otp.get_redis", fake_get_redis)
    response = await auth.login.__wrapped__(  # type: ignore[attr-defined]
        request=None,  # type: ignore[arg-type]
        req=auth.SmsLoginRequest(phone="13800138000", code="654321"),
        session=session,  # type: ignore[arg-type]
    )
    user_id = auth.decode_token(response.access_token)
    refreshed = await auth.refresh(user_id)

    assert isinstance(user_id, UUID)
    assert refreshed.user_id == str(user_id)
    assert session.commits == 1


@pytest.mark.asyncio
async def test_wrong_login_code_never_queries_user_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _AtomicRedis()
    session = _UserSession()

    async def fake_get_redis() -> _AtomicRedis:
        return redis

    monkeypatch.setattr("app.services.otp.get_redis", fake_get_redis)
    with pytest.raises(HTTPException) as exc_info:
        await auth.login.__wrapped__(  # type: ignore[attr-defined]
            request=None,  # type: ignore[arg-type]
            req=auth.SmsLoginRequest(phone="13800138000", code="000000"),
            session=session,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 401
    assert session.executions == 0


@pytest.mark.asyncio
async def test_local_guest_session_is_opt_in_and_returns_a_regular_jwt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _UserSession()
    monkeypatch.setattr(auth.settings, "LOCAL_GUEST_ACCESS", True)

    response = await auth.local_guest_login(session=session)  # type: ignore[arg-type]

    assert isinstance(auth.decode_token(response.access_token), UUID)
    assert response.user_id == str(auth.decode_token(response.access_token))
    assert session.added[0].phone == "local-guest"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_local_guest_session_is_rejected_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _UserSession()
    monkeypatch.setattr(auth.settings, "LOCAL_GUEST_ACCESS", False)

    with pytest.raises(HTTPException) as exc_info:
        await auth.local_guest_login(session=session)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 403
    assert session.executions == 0
