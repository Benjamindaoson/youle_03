from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Message(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str | None
    content_type: str = "text"
    extra_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
