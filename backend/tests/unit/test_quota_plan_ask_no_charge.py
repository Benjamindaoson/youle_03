"""配额铁律 20 回归测试:Plan / Ask 不扣任务配额(只扣 token)。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.quota_enforce import (
    QuotaExceeded,
    enforce_task_creation,
)


class _StubUser:
    """模拟 User ORM 实例(避免依赖真 DB)。"""

    def __init__(self, plan: str = "free") -> None:
        self.id = uuid4()
        self.plan = plan
        self.is_active = True


@pytest.mark.asyncio
async def test_plan_mode_does_not_consume_quota(monkeypatch) -> None:
    """work_mode=plan → 直接 return,不调用 _consumed / consume。"""
    consumed = MagicMock()
    monkeypatch.setattr("app.services.quota_enforce._consumed", consumed)
    consume = AsyncMock()
    monkeypatch.setattr("app.services.quota.QuotaService.consume", consume)

    fake_session = MagicMock()
    user = _StubUser()
    await enforce_task_creation(
        fake_session, user=user, work_mode="plan", task_kind="video"
    )
    consumed.assert_not_called()
    consume.assert_not_called()


@pytest.mark.asyncio
async def test_ask_mode_does_not_consume_quota(monkeypatch) -> None:
    """work_mode=ask → 同样不消耗任务配额。"""
    consumed = MagicMock()
    monkeypatch.setattr("app.services.quota_enforce._consumed", consumed)
    consume = AsyncMock()
    monkeypatch.setattr("app.services.quota.QuotaService.consume", consume)

    fake_session = MagicMock()
    user = _StubUser()
    await enforce_task_creation(
        fake_session, user=user, work_mode="ask", task_kind="image"
    )
    consumed.assert_not_called()
    consume.assert_not_called()


@pytest.mark.asyncio
async def test_auto_mode_does_consume_quota(monkeypatch) -> None:
    """对照组:Auto 模式必须扣配额(_consumed + consume 都被调用)。"""

    async def _consumed_stub(session, user_id, quota_type, period):
        return 0

    monkeypatch.setattr("app.services.quota_enforce._consumed", _consumed_stub)
    consume = AsyncMock()
    monkeypatch.setattr("app.services.quota.QuotaService.consume", consume)

    fake_session = MagicMock()
    user = _StubUser()
    await enforce_task_creation(
        fake_session, user=user, work_mode="auto", task_kind="text"
    )
    consume.assert_awaited()  # Auto 模式扣了


@pytest.mark.asyncio
async def test_auto_video_consumes_double(monkeypatch) -> None:
    """Auto 模式下视频任务额外扣 video_tasks_daily(共 2 次 consume)。"""

    async def _consumed_stub(session, user_id, quota_type, period):
        return 0

    monkeypatch.setattr("app.services.quota_enforce._consumed", _consumed_stub)
    consume = AsyncMock()
    monkeypatch.setattr("app.services.quota.QuotaService.consume", consume)

    fake_session = MagicMock()
    user = _StubUser(plan="personal")
    await enforce_task_creation(
        fake_session, user=user, work_mode="auto", task_kind="video"
    )
    assert consume.await_count == 2


@pytest.mark.asyncio
async def test_auto_quota_exhausted_raises(monkeypatch) -> None:
    """Auto 模式下达到日限额 → 抛 QuotaExceeded。"""

    async def _consumed_stub(session, user_id, quota_type, period):
        return 99999  # 远超

    monkeypatch.setattr("app.services.quota_enforce._consumed", _consumed_stub)

    fake_session = MagicMock()
    user = _StubUser()
    with pytest.raises(QuotaExceeded):
        await enforce_task_creation(
            fake_session, user=user, work_mode="auto", task_kind="text"
        )
