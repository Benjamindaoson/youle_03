"""No-key platform journey across auth, Skill, Agent, Redis, SSE, and UI contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from agents.orchestrator_agent.input_validator import validate_inputs
from agents.orchestrator_agent.skill_match import match_skill_with_confidence
from agents.orchestrator_agent.task_compiler import compile_task

from app.api.auth import _create_token, decode_token
from app.api.conversations import _members_for_mode
from app.models.conversation import Conversation
from app.models.skill import Skill
from app.models.task import Task
from app.schemas.agent import AgentResult, ArtifactRef
from app.schemas.events import EventType, UserEvent
from app.services import dispatcher
from app.services.event_bus import EventBus
from app.services.otp import consume_sms_otp, issue_sms_otp
from app.services.skill_loader import load_skill_by_id

ROOT = Path(__file__).resolve().parents[3]


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}

    async def setex(self, key: str, _ttl: int, value: str) -> None:
        self.values[key] = value

    async def eval(self, _script: str, _keys: int, key: str, expected: str) -> int:
        if self.values.get(key) != expected:
            return 0
        del self.values[key]
        return 1

    async def xadd(self, stream: str, fields: dict[str, str]) -> str:
        message_id = f"{len(self.streams.get(stream, [])) + 1}-0"
        self.streams.setdefault(stream, []).append((message_id, fields))
        return message_id

    async def xread(
        self, streams: dict[str, str], *, block: int, count: int
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        del block
        for stream in streams:
            messages = self.streams.get(stream, [])[:count]
            if messages:
                return [(stream, messages)]
        return []


class FakeScalars:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def all(self) -> list[Any]:
        return self.rows


class FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def scalars(self) -> FakeScalars:
        return FakeScalars(self.rows)


class SkillSession:
    def __init__(self, skill: Skill) -> None:
        self.skill = skill

    async def execute(self, _statement: Any) -> FakeResult:
        return FakeResult([self.skill])


@pytest.mark.asyncio
async def test_no_key_platform_journey(monkeypatch: pytest.MonkeyPatch) -> None:
    """A deterministic journey proves the cross-module handoffs without paid APIs."""
    redis = FakeRedis()
    phone = "13800138000"
    user_id = uuid4()

    # Login: the dev OTP is issued, atomically consumed once, and becomes a JWT identity.
    await issue_sms_otp(phone, redis=redis, dev_mode=True)
    assert await consume_sms_otp(phone, "123456", redis=redis)
    assert not await consume_sms_otp(phone, "123456", redis=redis)
    assert decode_token(_create_token(user_id)) == user_id

    # Group creation/member semantics use the canonical model and fixed five-Agent roster.
    conversation = Conversation(
        id=uuid4(),
        user_id=user_id,
        name="反诈视频制作群",
        mode="group",
        work_mode="auto",
        status="active",
    )
    members = _members_for_mode(conversation.mode)
    assert members == ["ceo_assistant", "agent_1", "agent_2", "agent_3", "agent_4"]

    # Skill matching uses the real matcher and the enabled built-in Skill metadata.
    skill_row = Skill(
        id=uuid4(),
        skill_id="anti_fraud_video",
        name="反诈视频制作",
        description="面向老年人的反诈短视频",
        domain="video",
        scenario="anti_fraud",
        version="1.0",
        creator_type="platform",
        visibility="public",
        status="published",
        keywords=["反诈", "老人"],
    )
    match = await match_skill_with_confidence(
        session=SkillSession(skill_row),  # type: ignore[arg-type]
        user_message="制作一条老人反诈视频",
        intent={"domain": "video", "scenario": "anti_fraud"},
    )
    assert match.skill is skill_row
    assert match.layer_used == "l1_exact"

    skill = load_skill_by_id(match.skill.skill_id)
    collected = {"年份": 2026, "骗局类型": "电信诈骗", "受众": "城市老人", "时长": "60s"}
    validation = validate_inputs(
        inputs_schema=skill["inputs_schema"], collected_fields=collected
    )
    assert validation.is_complete
    task_id, steps, agent_tasks = compile_task(
        skill_yaml=skill,
        collected_fields=validation.filled_fields,
        user_id=user_id,
        conversation_id=conversation.id,
    )
    task = Task(
        id=task_id,
        user_id=user_id,
        conversation_id=conversation.id,
        skill_id=skill_row.id,
        skill_version=skill_row.version,
        status="pending",
        collected_fields=validation.filled_fields,
        progress={"current": 0, "total": len(steps)},
    )
    assert task.status == "pending"
    assert agent_tasks[0].task_id == task.id

    # The canonical dispatcher serializes AgentTask to Redis; a no-key worker returns AgentResult.
    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(dispatcher, "get_redis", fake_get_redis)
    stream_id = await dispatcher.dispatch_task(agent_tasks[0])
    queue = dispatcher.QUEUE_BY_AGENT[agent_tasks[0].agent_id]
    assert stream_id == "1-0"
    assert '"skill_id":"anti_fraud_video"' in redis.streams[queue][0][1]["data"]

    result = AgentResult(
        task_id=task_id,
        step_id=agent_tasks[0].step_id,
        status="completed",
        output=ArtifactRef(
            artifact_id=uuid4(),
            type="document",
            reference="oss://mock/research.md",
        ),
        model_used="mock/no-key",
    )
    await redis.xadd(f"agent_results:{task_id}", {"data": result.model_dump_json()})
    received = await dispatcher.wait_for_result(str(task_id), timeout_seconds=1)
    assert received == result

    # The completion is delivered as the same UserEvent contract consumed by SSE and the frontend.
    bus = EventBus()
    queue_subscription = await bus.subscribe(str(user_id))
    event = UserEvent(
        type=EventType.TASK_COMPLETED,
        user_id=user_id,
        conversation_id=conversation.id,
        task_id=task_id,
        payload={"artifact": result.output.model_dump(mode="json")},
    )
    await bus.publish_to_user(str(user_id), event.model_dump(mode="json"))
    delivered = await queue_subscription.get()
    assert delivered["id"] == str(event.id)
    assert delivered["type"] == "task_completed"

    generated_types = (ROOT / "frontend" / "lib" / "api-types.ts").read_text(encoding="utf-8")
    frontend_adapter = (ROOT / "frontend" / "lib" / "ws-events.ts").read_text(encoding="utf-8")
    assert '"task_completed"' in generated_types
    assert "components['schemas']['UserEvent']" in frontend_adapter
