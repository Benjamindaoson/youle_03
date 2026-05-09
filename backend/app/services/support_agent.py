"""HR + 财务经理服务(铁律 18:仅主会话,不进队列,API 直接响应)。

ADR-013:HR 和财务经理是"支持 Agent",绕开 agent_tasks Redis Streams,
直接通过 app.router.complete 调用 LLM 并写回 messages 表。

V1 必做:
- HR:推荐 Agent / 解释能力边界 / 引导加 Skill
- 财务经理:配额查询 / 月度账单 / 升级续费 / 主动 80% 提醒(由独立检查器触发)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.prompts import (
    FINANCE_SYSTEM_PROMPT,
    HR_SYSTEM_PROMPT,
)
from app.models.message import Message
from app.models.quota import QuotaUsage
from app.router import complete
from app.services.conversation import append_message

log = structlog.get_logger(__name__)

# ── 配额套餐(财务经理回答需要)──
QUOTA_PLAN_LIMITS: dict[str, dict[str, int]] = {
    "free": {
        "auto_tasks_daily": 30,
        "video_tasks_daily": 3,
        "groups_monthly": 5,
        "plan_turns_per_group": 100,
    },
    "personal": {
        "auto_tasks_daily": 200,
        "video_tasks_daily": 20,
        "groups_monthly": 50,
        "plan_turns_per_group": 100,
    },
    "team": {
        "auto_tasks_daily": 2000,
        "video_tasks_daily": 200,
        "groups_monthly": 500,
        "plan_turns_per_group": 100,
    },
}


def _user_plan(user: Any) -> str:
    """读用户 plan 字段;缺省 free。"""
    return getattr(user, "plan", None) or "free"


# ── 历史上下文裁剪 ──
async def _recent_main_session_context(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    limit: int = 8,
) -> list[dict[str, str]]:
    """取最近 N 条消息作为上下文(role + content)。"""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    msgs = [
        {"role": "user" if m.role == "user" else "assistant", "content": m.content or ""}
        for m in reversed(rows)
        if m.content
    ]
    return msgs


# ── HR 服务 ──
async def hr_respond(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    user_message: str,
) -> Message:
    """HR 处理一条用户消息(team_management 类意图)→ 写一条 Message 回去。"""
    history = await _recent_main_session_context(
        session, conversation_id=conversation_id, limit=6
    )
    messages = [
        {"role": "system", "content": HR_SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_message},
    ]
    resp = await complete(
        task_type="intent_understanding",  # 走 deepseek-v4-flash 路由
        messages=messages,
        temperature=0.6,
        max_tokens=400,
    )
    text = resp.content
    log.info("support_agent.hr.respond", conversation_id=str(conversation_id))
    return await append_message(
        session,
        conversation_id=conversation_id,
        role="hr",
        content=text,
        extra_metadata={"agent_role": "hr"},
    )


# ── 财务经理服务 ──
async def finance_quota_summary(
    session: AsyncSession, *, user_id: UUID, plan: str = "free"
) -> dict[str, Any]:
    """读 QuotaUsage,组合成本月/今日实时使用画像。"""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    month = datetime.now(UTC).strftime("%Y-%m")
    rows = (
        await session.execute(
            select(QuotaUsage).where(
                QuotaUsage.user_id == user_id,
                QuotaUsage.period.in_([today, month]),
            )
        )
    ).scalars().all()
    used = {(r.quota_type, r.period): r.consumed for r in rows}
    limits = QUOTA_PLAN_LIMITS.get(plan, QUOTA_PLAN_LIMITS["free"])

    def _row(qtype: str, period: str) -> dict[str, int | float]:
        u = used.get((qtype, period), 0)
        total = limits.get(qtype, 0)
        return {
            "used": u,
            "total": total,
            "remaining": max(0, total - u),
            "percent": round(100 * u / total, 1) if total else 0.0,
        }

    return {
        "plan": plan,
        "auto_tasks_daily": _row("auto_tasks_daily", today),
        "video_tasks_daily": _row("video_tasks_daily", today),
        "groups_monthly": _row("groups_monthly", month),
    }


async def finance_respond(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    user_id: UUID,
    user_message: str,
    plan: str = "free",
) -> Message:
    """财务处理用户消息 → 自动注入实时配额画像 → LLM 生成回复。"""
    summary = await finance_quota_summary(session, user_id=user_id, plan=plan)
    quota_block = (
        "## 用户当前配额(实时)\n"
        f"- 套餐:{plan}\n"
        f"- 今日 Auto 任务:{summary['auto_tasks_daily']['used']}/"
        f"{summary['auto_tasks_daily']['total']} "
        f"(剩余 {summary['auto_tasks_daily']['remaining']})\n"
        f"- 今日视频任务:{summary['video_tasks_daily']['used']}/"
        f"{summary['video_tasks_daily']['total']}\n"
        f"- 本月新建群:{summary['groups_monthly']['used']}/"
        f"{summary['groups_monthly']['total']}\n"
    )
    history = await _recent_main_session_context(
        session, conversation_id=conversation_id, limit=6
    )
    messages = [
        {"role": "system", "content": FINANCE_SYSTEM_PROMPT + "\n\n" + quota_block},
        *history,
        {"role": "user", "content": user_message},
    ]
    resp = await complete(
        task_type="intent_understanding",
        messages=messages,
        temperature=0.4,
        max_tokens=400,
    )
    log.info("support_agent.finance.respond", user_id=str(user_id), plan=plan)
    return await append_message(
        session,
        conversation_id=conversation_id,
        role="finance_manager",
        content=resp.content,
        extra_metadata={"agent_role": "finance_manager", "quota_snapshot": summary},
    )


# ── 80% 提醒检查 ──
def needs_quota_warning(summary: dict[str, Any]) -> list[str]:
    """返回需要提醒的配额项 list(percent ≥ 80 且 < 100)。"""
    warned: list[str] = []
    for key in ("auto_tasks_daily", "video_tasks_daily", "groups_monthly"):
        row = summary.get(key, {})
        pct = row.get("percent", 0.0)
        if 80.0 <= pct < 100.0:
            warned.append(key)
    return warned


# ── 路由判定:消息属于 HR / Finance / 主编排 ──
def route_support_agent(intent_type: str, user_message: str) -> str | None:
    """根据意图与消息决定支持 Agent。返回 'hr' / 'finance' / None。

    主编排意图理解器已经会输出 team_management / quota_query;
    这里做一层兜底(显式 @HR / @财务 也走这里)。
    """
    msg = user_message.lower()
    if intent_type == "quota_query":
        return "finance"
    if intent_type == "team_management":
        return "hr"
    if "@财务" in user_message or "@finance" in msg:
        return "finance"
    if "@hr" in msg or "@人事" in user_message:
        return "hr"
    return None
