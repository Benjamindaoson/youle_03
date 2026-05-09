"""配额执行(v4 §40 #342-353)。

调用点:
- messages.py / runner.py 在创建 Auto Task 之前调 `enforce_task_creation`
- 视频任务额外日 3 次限制(单独 quota_type)
- 群创建在 conversations API 调 `enforce_group_creation`
- Plan 模式对话上限(每群 100 轮)由 messages.py 调 `enforce_plan_turn`

异常时抛 QuotaExceeded(HTTP 402-style),前端可弹财务经理对话引导升级。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.quota import QuotaUsage
from app.models.user import User
from app.services.quota import QuotaService
from app.services.support_agent import QUOTA_PLAN_LIMITS

log = structlog.get_logger(__name__)


# ── 异常 ──
class QuotaExceeded(Exception):
    """配额超限。`code` 决定前端弹什么提示。"""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


# ── 白名单(单独表 too small,这里直接 user.is_active + 标志位)──
async def is_whitelisted(session: AsyncSession, user_id: UUID) -> bool:
    """v4 #351:白名单/内测申请。简化为 user.plan != 'free' 或 user.is_active。"""
    user = await session.get(User, user_id)
    if user is None:
        return False
    return user.plan in ("personal", "team") or False


# ── Auto 任务创建闸门 ──
TaskKind = Literal["text", "image", "video", "document", "mixed"]


async def enforce_task_creation(
    session: AsyncSession,
    *,
    user: User,
    work_mode: str | None,
    task_kind: TaskKind = "text",
) -> None:
    """铁律 20 + v4 #342-347:
    - Plan / Ask 不扣任务配额(直接放行)
    - Auto 模式:扣 auto_tasks_daily;视频再加扣 video_tasks_daily
    """
    if work_mode != "auto":
        return  # Plan / Ask 不消耗任务配额

    plan = user.plan or "free"
    limits = QUOTA_PLAN_LIMITS.get(plan, QUOTA_PLAN_LIMITS["free"])

    # 原子检查+消费:单条 PostgreSQL conditional upsert,消除 TOCTOU 竞态
    ok = await QuotaService.try_consume(
        session,
        user_id=user.id,
        quota_type="auto_tasks_daily",
        limit=limits["auto_tasks_daily"],
    )
    if not ok:
        raise QuotaExceeded(
            "auto_tasks_daily_exhausted",
            f"今日 Auto 任务已用完(上限 {limits['auto_tasks_daily']})",
        )

    if task_kind == "video":
        ok = await QuotaService.try_consume(
            session,
            user_id=user.id,
            quota_type="video_tasks_daily",
            limit=limits["video_tasks_daily"],
        )
        if not ok:
            # 视频配额不够时需回退已消耗的 auto_tasks_daily
            await QuotaService.consume(
                session, user_id=user.id, quota_type="auto_tasks_daily", amount=-1
            )
            raise QuotaExceeded(
                "video_tasks_daily_exhausted",
                f"今日视频任务已用完(上限 {limits['video_tasks_daily']})",
            )


# ── 群创建闸门 ──
async def enforce_group_creation(session: AsyncSession, *, user: User) -> None:
    plan = user.plan or "free"
    limits = QUOTA_PLAN_LIMITS.get(plan, QUOTA_PLAN_LIMITS["free"])
    ok = await QuotaService.try_consume(
        session,
        user_id=user.id,
        quota_type="groups_monthly",
        limit=limits["groups_monthly"],
    )
    if not ok:
        raise QuotaExceeded(
            "groups_monthly_exhausted",
            f"本月新建群已用完(上限 {limits['groups_monthly']})",
        )


# ── Plan 模式对话上限(每群 100 轮)──
async def enforce_plan_turn(
    session: AsyncSession, *, conversation: Conversation, user: User
) -> None:
    if conversation.work_mode != "plan":
        return
    plan = user.plan or "free"
    limits = QUOTA_PLAN_LIMITS.get(plan, QUOTA_PLAN_LIMITS["free"])
    cap = limits["plan_turns_per_group"]
    turn_count = await session.scalar(
        select(func.count(Message.id)).where(
            Message.conversation_id == conversation.id,
            Message.role == "user",
        )
    )
    if (turn_count or 0) >= cap:
        raise QuotaExceeded(
            "plan_turns_exhausted",
            f"Plan 模式本群已 {turn_count} 轮(上限 {cap}),请切到 Auto 或新建群",
        )


# ── 工具 ──
async def _consumed(
    session: AsyncSession, user_id: UUID, quota_type: str, period: str
) -> int:
    row = await session.execute(
        select(QuotaUsage).where(
            QuotaUsage.user_id == user_id,
            QuotaUsage.quota_type == quota_type,
            QuotaUsage.period == period,
        )
    )
    usage = row.scalar_one_or_none()
    return int(usage.consumed) if usage else 0


# ── task_kind 推断(从 Skill / Workflow 中) ──
def infer_task_kind(skill_yaml: dict) -> TaskKind:
    """从 Skill YAML 推 task_kind,用于配额闸门。"""
    domain = (skill_yaml.get("domain") or "").lower()
    if domain in ("video", "av"):
        return "video"
    if domain == "image":
        return "image"
    if domain == "document":
        return "document"
    if domain == "mixed":
        return "mixed"
    return "text"
