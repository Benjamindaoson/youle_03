"""支持 Agent 路由 + 配额画像 单测。"""

from __future__ import annotations

from app.services.support_agent import (
    QUOTA_PLAN_LIMITS,
    needs_quota_warning,
    route_support_agent,
)


def test_route_team_management_goes_to_hr() -> None:
    assert route_support_agent("team_management", "我想加个新员工") == "hr"


def test_route_quota_query_goes_to_finance() -> None:
    assert route_support_agent("quota_query", "我还剩多少配额") == "finance"


def test_route_explicit_at_hr() -> None:
    assert route_support_agent("chitchat", "@HR 你能推荐一个 Agent 吗") == "hr"


def test_route_explicit_at_finance() -> None:
    assert route_support_agent("chitchat", "@财务 这个月用了多少") == "finance"


def test_route_normal_task_returns_none() -> None:
    assert route_support_agent("task_request", "做一个反诈视频") is None


def test_warning_at_80_percent() -> None:
    summary = {
        "auto_tasks_daily": {"used": 25, "total": 30, "remaining": 5, "percent": 83.3},
        "video_tasks_daily": {"used": 0, "total": 3, "remaining": 3, "percent": 0.0},
        "groups_monthly": {"used": 1, "total": 5, "remaining": 4, "percent": 20.0},
    }
    assert needs_quota_warning(summary) == ["auto_tasks_daily"]


def test_warning_skipped_at_100_percent() -> None:
    summary = {
        "auto_tasks_daily": {"used": 30, "total": 30, "remaining": 0, "percent": 100.0},
        "video_tasks_daily": {"used": 0, "total": 3, "remaining": 3, "percent": 0.0},
        "groups_monthly": {"used": 0, "total": 5, "remaining": 5, "percent": 0.0},
    }
    assert needs_quota_warning(summary) == []


def test_quota_plan_limits_keys() -> None:
    for plan in ("free", "personal", "team"):
        limits = QUOTA_PLAN_LIMITS[plan]
        assert "auto_tasks_daily" in limits
        assert "video_tasks_daily" in limits
        assert "groups_monthly" in limits
        assert limits["auto_tasks_daily"] >= limits["video_tasks_daily"]
