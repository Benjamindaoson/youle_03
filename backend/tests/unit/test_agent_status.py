"""Agent 状态派生单测。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.agent_status import FISHING_THRESHOLD, derive_status


def test_working_passthrough() -> None:
    assert derive_status(current="working", last_active_at=datetime.now(UTC)) == "working"


def test_training_passthrough() -> None:
    assert derive_status(current="training", last_active_at=datetime.now(UTC)) == "training"


def test_idle_under_30min_stays_idle() -> None:
    last = datetime.now(UTC) - timedelta(minutes=10)
    assert derive_status(current="idle", last_active_at=last) == "idle"


def test_idle_over_30min_becomes_fishing() -> None:
    last = datetime.now(UTC) - FISHING_THRESHOLD - timedelta(minutes=1)
    assert derive_status(current="idle", last_active_at=last) == "fishing"


def test_fishing_within_recent_collapses_to_idle() -> None:
    """当前 fishing 但活跃时间被刷新到 5 分钟前 → 应回到 idle。"""
    last = datetime.now(UTC) - timedelta(minutes=5)
    assert derive_status(current="fishing", last_active_at=last) == "idle"
