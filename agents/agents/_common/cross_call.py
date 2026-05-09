"""Agent 跨调防御(ADR-002):永久 NotImplementedError。

铁律 3:跨能力步骤显式拆步,不在 handler 里跨调。
"""

from __future__ import annotations

from typing import Any


def call_other_agent(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError(
        "ADR-002:Agent 不主动跨调其他 Agent。请在 Skill YAML 显式拆步。"
    )
