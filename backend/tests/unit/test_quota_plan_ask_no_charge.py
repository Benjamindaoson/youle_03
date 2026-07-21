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
    """对照组:Auto 模式必须原子检查并扣减配额。"""
    try_consume = AsyncMock(return_value=True)
    monkeypatch.setattr("app.services.quota.QuotaService.try_consume", try_consume)

    fake_session = MagicMock()
    user = _StubUser()
    await enforce_task_creation(
        fake_session, user=user, work_mode="auto", task_kind="text"
    )
    try_consume.assert_awaited_once()


@pytest.mark.asyncio
async def test_auto_video_consumes_double(monkeypatch) -> None:
    """Auto 模式下视频任务额外扣 video_tasks_daily。"""
    try_consume = AsyncMock(return_value=True)
    monkeypatch.setattr("app.services.quota.QuotaService.try_consume", try_consume)

    fake_session = MagicMock()
    user = _StubUser(plan="personal")
    await enforce_task_creation(
        fake_session, user=user, work_mode="auto", task_kind="video"
    )
    assert try_consume.await_count == 2


@pytest.mark.asyncio
async def test_auto_quota_exhausted_raises(monkeypatch) -> None:
    """Auto 模式下达到日限额 → 抛 QuotaExceeded。"""

    try_consume = AsyncMock(return_value=False)
    monkeypatch.setattr("app.services.quota.QuotaService.try_consume", try_consume)

    fake_session = MagicMock()
    user = _StubUser()
    with pytest.raises(QuotaExceeded):
        await enforce_task_creation(
            fake_session, user=user, work_mode="auto", task_kind="text"
        )
