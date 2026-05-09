from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

GateType = Literal["version_select", "quality_review", "final_approval"]
Resolution = Literal["approved", "modified", "rolled_back", "timeout"]


class HITLGate(BaseModel):
    id: UUID
    task_id: UUID
    step_id: str
    gate_type: GateType
    timeout_seconds: int = 600
    resolution: Resolution | None = None
    user_choice: dict[str, Any] | None = None
    extra_metadata: dict[str, Any] = Field(default_factory=dict)
