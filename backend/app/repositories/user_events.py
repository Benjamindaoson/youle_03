from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_event import UserEventRecord
from app.schemas.events import UserEvent


class UserEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, event: UserEvent) -> UserEventRecord:
        row = UserEventRecord(
            id=event.id,
            type=event.type.value,
            user_id=event.user_id,
            conversation_id=event.conversation_id,
            task_id=event.task_id,
            agent_id=event.agent_id,
            payload=event.payload,
            created_at=event.created_at,
        )
        self._session.add(row)
        await self._session.flush([row])
        return row

    async def replay(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        after_event_id: UUID | None = None,
        limit: int = 500,
    ) -> list[UserEventRecord]:
        stream_scope = and_(
            UserEventRecord.user_id == user_id,
            or_(
                UserEventRecord.conversation_id == conversation_id,
                UserEventRecord.conversation_id.is_(None),
            ),
        )
        cursor: UserEventRecord | None = None
        if after_event_id is not None:
            cursor = await self._session.scalar(
                select(UserEventRecord).where(
                    stream_scope, UserEventRecord.id == after_event_id
                )
            )
            if cursor is None:
                return []

        statement = select(UserEventRecord).where(stream_scope)
        if cursor is not None:
            statement = statement.where(
                or_(
                    UserEventRecord.created_at > cursor.created_at,
                    and_(
                        UserEventRecord.created_at == cursor.created_at,
                        UserEventRecord.id > cursor.id,
                    ),
                )
            )
        rows = await self._session.execute(
            statement.order_by(
                UserEventRecord.created_at.asc(), UserEventRecord.id.asc()
            ).limit(limit)
        )
        return list(rows.scalars().all())
