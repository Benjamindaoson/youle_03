"""配额服务(铁律 20:Plan/Ask 不扣任务配额,只算 token)。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quota import QuotaUsage

log = structlog.get_logger(__name__)


class QuotaService:
    @staticmethod
    def _today() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d")

    @staticmethod
    def _month() -> str:
        return datetime.now(UTC).strftime("%Y-%m")

    @classmethod
    async def consume(
        cls,
        session: AsyncSession,
        *,
        user_id: UUID,
        quota_type: str,
        amount: int = 1,
    ) -> None:
        period = cls._today() if quota_type.endswith("_daily") else cls._month()
        stmt = (
            pg_insert(QuotaUsage)
            .values(
                user_id=user_id,
                quota_type=quota_type,
                period=period,
                consumed=amount,
                last_used_at=datetime.now(UTC),
            )
            .on_conflict_do_update(
                index_elements=["user_id", "quota_type", "period"],
                set_={
                    "consumed": QuotaUsage.consumed + amount,
                    "last_used_at": datetime.now(UTC),
                },
            )
        )
        await session.execute(stmt)
        await session.commit()

    @classmethod
    async def try_consume(
        cls,
        session: AsyncSession,
        *,
        user_id: UUID,
        quota_type: str,
        limit: int,
        amount: int = 1,
    ) -> bool:
        """Atomically check-and-consume quota in a single DB round-trip.

        Uses PostgreSQL conditional upsert: the ON CONFLICT UPDATE only fires
        when existing consumed < limit, so concurrent requests cannot both pass
        a separate check-then-set.  Returns False if limit is already reached.
        """
        if amount > limit:
            return False
        period = cls._today() if quota_type.endswith("_daily") else cls._month()
        stmt = (
            pg_insert(QuotaUsage)
            .values(
                user_id=user_id,
                quota_type=quota_type,
                period=period,
                consumed=amount,
                last_used_at=datetime.now(UTC),
            )
            .on_conflict_do_update(
                index_elements=["user_id", "quota_type", "period"],
                set_={
                    "consumed": QuotaUsage.consumed + amount,
                    "last_used_at": datetime.now(UTC),
                },
                where=QuotaUsage.consumed < limit,
            )
            .returning(QuotaUsage.consumed)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one_or_none() is not None

    @classmethod
    async def remaining(
        cls, session: AsyncSession, *, user_id: UUID, quota_type: str, total: int
    ) -> int:
        period = cls._today() if quota_type.endswith("_daily") else cls._month()
        row = await session.execute(
            select(QuotaUsage).where(
                QuotaUsage.user_id == user_id,
                QuotaUsage.quota_type == quota_type,
                QuotaUsage.period == period,
            )
        )
        usage = row.scalar_one_or_none()
        consumed = usage.consumed if usage else 0
        return max(0, total - consumed)
