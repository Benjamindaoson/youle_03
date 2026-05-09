from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
AGENTS_ROOT = ROOT / "agents"
if str(AGENTS_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENTS_ROOT))


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(ROOT / ".env")
_load_env_file(AGENTS_ROOT / ".env")
os.environ["LITELLM_MOCK"] = "false"


@pytest.mark.asyncio
async def test_agent1_short_writing_live_api(monkeypatch):
    import agents._common.llm as llm
    from agents._common.protocol import AgentTask
    import agents.text_agent.handlers.short_writing as short_writing

    importlib.reload(llm)
    importlib.reload(short_writing)

    captured: dict[str, str] = {}

    async def fake_put_text(*, key, content, content_type="text/plain"):
        captured["key"] = key
        captured["content"] = content
        captured["content_type"] = content_type
        return f"oss://live-test/{key}"

    monkeypatch.setattr(short_writing, "put_text", fake_put_text)

    task = AgentTask(
        task_id=uuid4(),
        step_id="short_writing_live",
        agent_id="agent_1",
        task_type="short_writing",
        user_id=uuid4(),
        conversation_id=uuid4(),
        inputs={
            "_prompt": "给一家社区咖啡店写一条中文朋友圈短文案，25字以内，温暖但不夸张。"
        },
        parameters={"max_tokens": 80},
        routing_hints={},
        timeout_seconds=180,
    )

    result = await short_writing.short_writing_handler(task)

    assert result.status == "completed"
    assert result.step_id == "short_writing_live"
    assert result.output is not None
    assert result.output.type == "text"
    assert result.output.reference.startswith("oss://live-test/artifacts/")
    assert result.model_used
    assert captured["content"].strip()
