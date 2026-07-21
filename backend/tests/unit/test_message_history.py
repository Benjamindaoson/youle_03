from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.messages import list_messages
from app.models.conversation import Conversation
from app.models.message import Message


class _Scalars:
    def __init__(self, rows: list[Message]) -> None:
        self.rows = rows

    def scalars(self) -> _Scalars:
        return self

    def all(self) -> list[Message]:
        return self.rows


class _Session:
    def __init__(self, conversation: Conversation, rows: list[Message]) -> None:
        self.conversation = conversation
        self.rows = rows
        self.statement: Any = None

    async def get(self, _model: Any, _key: Any) -> Conversation:
        return self.conversation

    async def execute(self, statement: Any) -> _Scalars:
        self.statement = statement
        return _Scalars(self.rows)


@pytest.mark.asyncio
async def test_message_history_is_owner_scoped_and_chronological() -> None:
    user_id = uuid4()
    conversation = Conversation(
        id=uuid4(), user_id=user_id, name="group", mode="group"
    )
    rows = [Message(id=uuid4(), conversation_id=conversation.id, role="user")]
    session = _Session(conversation, rows)

    result = await list_messages(
        conversation.id, user_id=user_id, session=session  # type: ignore[arg-type]
    )

    assert result == rows
    assert "messages.created_at ASC" in str(session.statement)


@pytest.mark.asyncio
async def test_message_history_rejects_foreign_conversation() -> None:
    conversation = Conversation(
        id=uuid4(), user_id=uuid4(), name="private", mode="private_chat"
    )
    session = _Session(conversation, [])

    with pytest.raises(HTTPException) as exc_info:
        await list_messages(
            conversation.id,
            user_id=uuid4(),
            session=session,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 403
