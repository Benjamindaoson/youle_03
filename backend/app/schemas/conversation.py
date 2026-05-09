from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

ConversationMode = Literal["main_session", "group", "private_chat"]
WorkMode = Literal["plan", "ask", "auto"]


class Conversation(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    mode: ConversationMode
    work_mode: WorkMode | None
    skill_id: UUID | None
    status: str
