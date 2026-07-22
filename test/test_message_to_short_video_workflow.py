from __future__ import annotations

import os
import sys
import asyncio
import contextlib
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
AGENTS_ROOT = ROOT / "agents"
BACKEND_ROOT = ROOT / "backend"
for path in (str(BACKEND_ROOT), str(AGENTS_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


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
os.environ["DEBUG"] = "true"
os.environ["LITELLM_MOCK"] = "true"

pytestmark = pytest.mark.skipif(
    os.getenv("HAOLE_RUN_LIVE_TESTS") != "1",
    reason="requires explicit HAOLE_RUN_LIVE_TESTS=1 with PostgreSQL and Redis",
)


@pytest.mark.asyncio
async def test_message_prompt_starts_short_video_workflow(monkeypatch):
    from app.api import messages as messages_api
    from app.api.messages import SendMessageRequest, send_message
    from app.db import SessionLocal, engine
    from app.models.conversation import Conversation
    from app.models.skill import Skill
    from app.models.task import Task
    from app.models.user import User
    from agents.orchestrator_agent.intent import Intent
    from sqlalchemy import select

    await engine.dispose()

    started_task_ids: list[str] = []

    async def fake_understand_intent(*, user_message, recent_history=None, conversation_context=None):
        return Intent(
            intent_type="task_request",
            domain="video",
            scenario="short_video",
            entities={
                "主题": "城市漫游",
                "风格": "治愈向",
                "受众": "都市白领",
                "时长": "60s",
            },
            confidence=0.99,
        )

    class RecordingRunner:
        def __init__(self, session):
            self.session = session

        async def start(self, task_id):
            started_task_ids.append(str(task_id))
            return {"state": "recorded", "entry_step": "research"}

    monkeypatch.setattr(messages_api, "understand_intent", fake_understand_intent)
    monkeypatch.setattr(messages_api, "make_runner", lambda session: RecordingRunner(session))

    skill_path = ROOT / "backend" / "skills" / "playbooks" / "short_video.yaml"
    skill_yaml_text = skill_path.read_text(encoding="utf-8")
    skill_yaml = yaml.safe_load(skill_yaml_text)

    user_id = uuid4()
    conv_id = uuid4()
    skill_db_id = uuid4()

    async with SessionLocal() as session:
        user = User(id=user_id, phone=f"139{str(user_id.int)[-8:]}", nickname="message-flow-test", plan="free")
        session.add(user)
        existing_skill = (
            await session.execute(select(Skill).where(Skill.skill_id == "short_video"))
        ).scalar_one_or_none()
        if existing_skill is None:
            skill = Skill(
                id=skill_db_id,
                skill_id="short_video",
                name=skill_yaml["name"],
                description=skill_yaml.get("description"),
                domain=skill_yaml.get("domain"),
                scenario=skill_yaml.get("scenario"),
                version=str(skill_yaml.get("version", "1.0")),
                visibility="public",
                keywords=skill_yaml.get("keywords", []),
                anti_signals=skill_yaml.get("anti_signals", []),
                yaml_content=skill_yaml_text,
                inputs_schema={"items": skill_yaml.get("inputs_schema", [])},
                workflow_steps={"items": skill_yaml.get("workflow", [])},
                status="published",
            )
            session.add(skill)
        else:
            skill = existing_skill
            skill.name = skill_yaml["name"]
            skill.domain = skill_yaml.get("domain")
            skill.scenario = skill_yaml.get("scenario")
            skill.version = str(skill_yaml.get("version", "1.0"))
            skill.visibility = "public"
            skill.status = "published"
            skill.yaml_content = skill_yaml_text
        await session.flush()
        skill_db_id = skill.id
        conv = Conversation(
            id=conv_id,
            user_id=user_id,
            name="短视频测试群",
            mode="group",
            work_mode="auto",
            skill_id=skill_db_id,
        )
        session.add(conv)
        await session.commit()

        response = await send_message(
            conv_id,
            SendMessageRequest(
                content="帮我做一个60秒城市漫游短视频，治愈风，给都市白领看。"
            ),
            session,
        )

        task = await session.get(Task, response.payload["task_id"])

    assert response.decision == "task_started"
    assert response.payload["skill_id"] == "short_video"
    assert response.payload["step_count"] == 5
    assert started_task_ids == [response.payload["task_id"]]
    assert task is not None
    assert task.skill_id == skill_db_id
    assert task.skill_version == "1.0"
    assert task.collected_fields == {
        "主题": "城市漫游",
        "风格": "治愈向",
        "受众": "都市白领",
        "时长": "60s",
    }


@pytest.mark.asyncio
async def test_message_prompt_runs_short_video_until_hitl_with_real_runner(monkeypatch):
    from agents._common.consumer import AgentConsumer
    from agents.image_agent.handlers.image_download import image_download_handler
    from agents.text_agent.handlers.long_writing import long_writing_handler
    from agents.text_agent.handlers.web_search import web_search_handler
    from app.api import messages as messages_api
    from app.api.messages import SendMessageRequest, send_message
    from app.db import SessionLocal, engine
    from app.models.conversation import Conversation
    from app.models.hitl_gate import HITLGate
    from app.models.skill import Skill
    from app.models.task import Task, TaskStep
    from app.models.user import User
    from agents.orchestrator_agent.intent import Intent
    from app.redis_client import close_redis
    from sqlalchemy import select

    await close_redis()
    await engine.dispose()

    async def fake_understand_intent(*, user_message, recent_history=None, conversation_context=None):
        return Intent(
            intent_type="task_request",
            domain="video",
            scenario="short_video",
            entities={
                "主题": "城市漫游",
                "风格": "治愈向",
                "受众": "都市白领",
                "时长": "60s",
            },
            confidence=0.99,
        )

    async def fake_put_json(*, key, payload):
        return f"oss://message-flow/{key}"

    async def fake_put_text(*, key, content, content_type="text/plain"):
        return f"oss://message-flow/{key}"

    async def fake_emit(*, signal_type, payload):
        return None

    async def fake_call_tool(*, server, tool, arguments):
        if (server, tool) == ("search", "web_search"):
            return {
                "results": [
                    {
                        "title": "2026 城市漫游案例",
                        "url": "https://example.com/short-video",
                        "snippet": "适合城市漫游主题的街区与步道素材。",
                        "image_url": "https://example.com/a.jpg",
                    }
                ]
            }
        if (server, tool) == ("image_tools", "download_batch"):
            return {"oss_ref": "oss://message-flow/images/", "downloaded_count": 5, "rejected_count": 0}
        return {}

    monkeypatch.setattr(messages_api, "understand_intent", fake_understand_intent)
    monkeypatch.setattr("agents.text_agent.handlers.web_search.put_json", fake_put_json)
    monkeypatch.setattr("agents.text_agent.handlers.long_writing.put_text", fake_put_text)
    monkeypatch.setattr("agents.text_agent.handlers.web_search.emit", fake_emit)
    monkeypatch.setattr("agents._common.mcp_client.mcp_client.call_tool", fake_call_tool)

    agent1 = AgentConsumer(
        agent_id="agent_1",
        handlers={"web_search": web_search_handler, "long_writing": long_writing_handler},
        consumer_name=f"message-flow-agent1-{uuid4().hex}",
    )
    agent3 = AgentConsumer(
        agent_id="agent_3",
        handlers={"image_download": image_download_handler},
        consumer_name=f"message-flow-agent3-{uuid4().hex}",
    )
    await agent1._r()
    await agent3._r()
    agent_tasks = [asyncio.create_task(agent1.start()), asyncio.create_task(agent3.start())]

    skill_path = ROOT / "backend" / "skills" / "playbooks" / "short_video.yaml"
    skill_yaml_text = skill_path.read_text(encoding="utf-8")
    skill_yaml = yaml.safe_load(skill_yaml_text)

    user_id = uuid4()
    conv_id = uuid4()
    async with SessionLocal() as session:
        try:
            user = User(id=user_id, phone=f"137{str(user_id.int)[-8:]}", nickname="message-real-runner", plan="free")
            session.add(user)
            existing_skill = (
                await session.execute(select(Skill).where(Skill.skill_id == "short_video"))
            ).scalar_one_or_none()
            if existing_skill is None:
                skill = Skill(
                    id=uuid4(),
                    skill_id="short_video",
                    name=skill_yaml["name"],
                    description=skill_yaml.get("description"),
                    domain=skill_yaml.get("domain"),
                    scenario=skill_yaml.get("scenario"),
                    version=str(skill_yaml.get("version", "1.0")),
                    visibility="public",
                    keywords=skill_yaml.get("keywords", []),
                    anti_signals=skill_yaml.get("anti_signals", []),
                    yaml_content=skill_yaml_text,
                    inputs_schema={"items": skill_yaml.get("inputs_schema", [])},
                    workflow_steps={"items": skill_yaml.get("workflow", [])},
                    status="published",
                )
                session.add(skill)
            else:
                skill = existing_skill
                skill.yaml_content = skill_yaml_text
                skill.scenario = "short_video"
                skill.domain = "video"
                skill.visibility = "public"
                skill.status = "published"
            await session.flush()
            conv = Conversation(
                id=conv_id,
                user_id=user_id,
                name="短视频真实 runner 测试群",
                mode="group",
                work_mode="auto",
                skill_id=skill.id,
            )
            session.add(conv)
            await session.commit()

            response = await send_message(
                conv_id,
                SendMessageRequest(
                    content="帮我做一个60秒城市漫游短视频，治愈风，给都市白领看。"
                ),
                session,
            )

            task_id = response.payload["task_id"]
            task = await session.get(Task, task_id)
            steps = (
                await session.execute(select(TaskStep).where(TaskStep.task_id == task_id))
            ).scalars().all()
            gates = (
                await session.execute(select(HITLGate).where(HITLGate.task_id == task_id))
            ).scalars().all()
        finally:
            agent1.stop()
            agent3.stop()
            for task_handle in agent_tasks:
                task_handle.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task_handle
            await close_redis()

    step_status = {step.step_id: step.status for step in steps}
    assert response.decision == "task_started"
    assert response.payload["skill_id"] == "short_video"
    assert task is not None
    assert task.status == "executing"
    assert step_status["research"] == "completed"
    assert "script" in step_status or "image_process" in step_status
    assert gates, "real runner should pause on a HITL gate after early short_video steps"


@pytest.mark.asyncio
async def test_message_prompt_completes_full_short_video_workflow(monkeypatch):
    from agents._common.consumer import AgentConsumer
    from agents.av_agent.handlers import bgm_select as bgm_module
    from agents.av_agent.handlers import video_compose as video_compose_module
    from agents.av_agent.handlers.bgm_select import bgm_select_handler
    from agents.av_agent.handlers.video_compose import video_compose_handler
    from agents.image_agent.handlers.image_download import image_download_handler
    from agents.text_agent.handlers.long_writing import long_writing_handler
    from agents.text_agent.handlers.web_search import web_search_handler
    from app.api import messages as messages_api
    from app.api.messages import SendMessageRequest, send_message
    from app.db import SessionLocal, engine
    from app.models.conversation import Conversation
    from app.models.hitl_gate import HITLGate
    from app.models.skill import Skill
    from app.models.task import Task, TaskStep
    from app.models.user import User
    from agents.orchestrator_agent.intent import Intent
    from agents.orchestrator_agent.runner_factory import make_runner
    from app.redis_client import close_redis
    from sqlalchemy import select

    await close_redis()
    await engine.dispose()

    async def fake_understand_intent(*, user_message, recent_history=None, conversation_context=None):
        return Intent(
            intent_type="task_request",
            domain="video",
            scenario="short_video",
            entities={
                "主题": "城市漫游",
                "风格": "治愈向",
                "受众": "都市白领",
                "时长": "60s",
            },
            confidence=0.99,
        )

    async def fake_put_json(*, key, payload):
        return f"oss://message-flow/{key}"

    async def fake_put_text(*, key, content, content_type="text/plain"):
        return f"oss://message-flow/{key}"

    async def fake_emit(*, signal_type, payload):
        return None

    async def fake_call_tool(*, server, tool, arguments):
        if (server, tool) == ("search", "web_search"):
            return {
                "results": [
                    {
                        "title": "2026 城市漫游案例",
                        "url": "https://example.com/short-video",
                        "snippet": "适合城市漫游主题的街区与步道素材。",
                        "image_url": "https://example.com/a.jpg",
                    },
                    {
                        "title": "滨江步道主题",
                        "url": "https://example.com/short-video-2",
                        "snippet": "适合清晨拍摄，光线柔和且步行友好。",
                        "image_url": "https://example.com/b.jpg",
                    },
                ]
            }
        if (server, tool) == ("image_tools", "download_batch"):
            return {"oss_ref": "oss://message-flow/images/", "downloaded_count": 5, "rejected_count": 0}
        return {}

    class FakeEngine:
        async def dispose(self):
            return None

    class FakeRows:
        def first(self):
            return None

    class FakeBgmSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, *args, **kwargs):
            return FakeRows()

    class FakeSessionMaker:
        def __call__(self):
            return FakeBgmSession()

    class FakeVideoWorkflow:
        id = "message-flow-video-workflow-id"

    def fake_video_delay(task_payload_json):
        import redis

        payload = json.loads(task_payload_json)
        task_id = payload["task_id"]
        step_id = payload["step_id"]

        def push_completed_result():
            result_payload = {
                "task_id": task_id,
                "step_id": step_id,
                "status": "completed",
                "output": {
                    "artifact_id": str(uuid4()),
                    "type": "video",
                    "reference": f"oss://message-flow/artifacts/{task_id}/{step_id}.mp4",
                    "extra_metadata": {
                        "duration_seconds": 60,
                        "resolution": "1080x1920",
                        "mock_celery": True,
                    },
                },
                "duration_ms": 1,
                "model_used": "mock-video-compose",
            }
            client = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
            try:
                client.xadd(f"agent_results:{task_id}", {"data": json.dumps(result_payload)})
            finally:
                client.close()

        threading.Timer(0.05, push_completed_result).start()
        return FakeVideoWorkflow()

    monkeypatch.setattr(messages_api, "understand_intent", fake_understand_intent)
    monkeypatch.setattr("agents.text_agent.handlers.web_search.put_json", fake_put_json)
    monkeypatch.setattr("agents.text_agent.handlers.long_writing.put_text", fake_put_text)
    monkeypatch.setattr("agents.text_agent.handlers.web_search.emit", fake_emit)
    monkeypatch.setattr("agents._common.mcp_client.mcp_client.call_tool", fake_call_tool)
    monkeypatch.setattr(bgm_module, "create_async_engine", lambda *args, **kwargs: FakeEngine())
    monkeypatch.setattr(bgm_module, "async_sessionmaker", lambda *args, **kwargs: FakeSessionMaker())
    monkeypatch.setattr(
        video_compose_module,
        "video_compose_workflow",
        SimpleNamespace(delay=fake_video_delay),
    )

    consumers = [
        AgentConsumer(
            agent_id="agent_1",
            handlers={"web_search": web_search_handler, "long_writing": long_writing_handler},
            consumer_name=f"full-flow-agent1-{uuid4().hex}",
        ),
        AgentConsumer(
            agent_id="agent_3",
            handlers={"image_download": image_download_handler},
            consumer_name=f"full-flow-agent3-{uuid4().hex}",
        ),
        AgentConsumer(
            agent_id="agent_4",
            handlers={"bgm_select": bgm_select_handler, "video_compose": video_compose_handler},
            consumer_name=f"full-flow-agent4-{uuid4().hex}",
        ),
    ]
    for consumer in consumers:
        await consumer._r()
    consumer_tasks = [asyncio.create_task(consumer.start()) for consumer in consumers]

    skill_path = ROOT / "backend" / "skills" / "playbooks" / "short_video.yaml"
    skill_yaml_text = skill_path.read_text(encoding="utf-8")
    skill_yaml = yaml.safe_load(skill_yaml_text)

    user_id = uuid4()
    conv_id = uuid4()
    async with SessionLocal() as session:
        try:
            user = User(id=user_id, phone=f"136{str(user_id.int)[-8:]}", nickname="message-full-runner", plan="free")
            session.add(user)
            existing_skill = (
                await session.execute(select(Skill).where(Skill.skill_id == "short_video"))
            ).scalar_one_or_none()
            if existing_skill is None:
                skill = Skill(
                    id=uuid4(),
                    skill_id="short_video",
                    name=skill_yaml["name"],
                    description=skill_yaml.get("description"),
                    domain=skill_yaml.get("domain"),
                    scenario=skill_yaml.get("scenario"),
                    version=str(skill_yaml.get("version", "1.0")),
                    visibility="public",
                    keywords=skill_yaml.get("keywords", []),
                    anti_signals=skill_yaml.get("anti_signals", []),
                    yaml_content=skill_yaml_text,
                    inputs_schema={"items": skill_yaml.get("inputs_schema", [])},
                    workflow_steps={"items": skill_yaml.get("workflow", [])},
                    status="published",
                )
                session.add(skill)
            else:
                skill = existing_skill
                skill.yaml_content = skill_yaml_text
                skill.scenario = "short_video"
                skill.domain = "video"
                skill.visibility = "public"
                skill.status = "published"
            await session.flush()
            conv = Conversation(
                id=conv_id,
                user_id=user_id,
                name="短视频完整工作流测试群",
                mode="group",
                work_mode="auto",
                skill_id=skill.id,
            )
            session.add(conv)
            await session.commit()

            response = await send_message(
                conv_id,
                SendMessageRequest(
                    content="帮我做一个60秒城市漫游短视频，治愈风，给都市白领看。"
                ),
                session,
            )

            task_id = response.payload["task_id"]
            runner = make_runner(session)
            approved_steps: list[str] = []
            for _ in range(5):
                gates = (
                    await session.execute(
                        select(HITLGate)
                        .where(HITLGate.task_id == task_id, HITLGate.closed_at.is_(None))
                        .order_by(HITLGate.opened_at)
                    )
                ).scalars().all()
                if not gates:
                    break
                gate = gates[0]
                approved_steps.append(gate.step_id)
                await runner.resolve_hitl(
                    gate.id,
                    resolution="approved",
                    user_choice={"approved_by": "live_test", "step_id": gate.step_id},
                )

            task = await session.get(Task, task_id)
            steps = (
                await session.execute(select(TaskStep).where(TaskStep.task_id == task_id))
            ).scalars().all()
            all_gates = (
                await session.execute(select(HITLGate).where(HITLGate.task_id == task_id))
            ).scalars().all()
        finally:
            for consumer in consumers:
                consumer.stop()
            for task_handle in consumer_tasks:
                task_handle.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task_handle
            await close_redis()

    step_status = {step.step_id: step.status for step in steps}
    gate_status = {gate.step_id: gate.resolution for gate in all_gates}
    assert response.decision == "task_started"
    assert task is not None
    assert task.status == "completed"
    assert step_status == {
        "research": "completed",
        "script": "completed",
        "image_process": "completed",
        "bgm": "completed",
        "video_compose": "completed",
    }
    assert approved_steps == ["script", "image_process", "video_compose"]
    assert gate_status == {
        "script": "approved",
        "image_process": "approved",
        "video_compose": "approved",
    }
