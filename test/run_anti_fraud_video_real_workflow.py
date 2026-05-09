from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import boto3
import yaml
from botocore.client import Config

ROOT = Path(__file__).resolve().parents[1]
AGENTS_ROOT = ROOT / "agents"
BACKEND_ROOT = ROOT / "backend"
for path in (str(BACKEND_ROOT), str(AGENTS_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


load_env(ROOT / ".env")
load_env(AGENTS_ROOT / ".env")
os.environ["DEBUG"] = "false"
os.environ["LITELLM_MOCK"] = "false"
os.environ["YOULE_AUTO_APPROVE_HITL"] = "true"
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1,::1")


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("OSS_ENDPOINT", "http://localhost:9000"),
        aws_access_key_id=os.getenv("OSS_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.getenv("OSS_SECRET_KEY", "minioadmin"),
        region_name=os.getenv("OSS_REGION", "cn-hangzhou"),
        config=Config(signature_version="s3v4"),
    )


def parse_oss_ref(ref: str) -> tuple[str, str]:
    rest = ref.removeprefix("oss://")
    bucket, _, key = rest.partition("/")
    return bucket, key


async def main() -> None:
    from agents._common.consumer import AgentConsumer
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
    from agents.orchestrator_agent.runner_factory import make_runner
    from app.redis_client import close_redis
    from sqlalchemy import select

    await close_redis()
    await engine.dispose()

    async def no_mode_switch(*, current_mode, conversation_name, message):
        from agents.orchestrator_agent.mode_manager import ModeSwitchSignal

        return ModeSwitchSignal(switch_to=None, confidence=0.0)

    messages_api.detect_mode_switch = no_mode_switch

    consumers = [
        AgentConsumer(
            agent_id="agent_1",
            handlers={"web_search": web_search_handler, "long_writing": long_writing_handler},
            consumer_name=f"real-anti-fraud-agent1-{uuid4().hex}",
        ),
        AgentConsumer(
            agent_id="agent_3",
            handlers={"image_download": image_download_handler},
            consumer_name=f"real-anti-fraud-agent3-{uuid4().hex}",
        ),
        AgentConsumer(
            agent_id="agent_4",
            handlers={"bgm_select": bgm_select_handler, "video_compose": video_compose_handler},
            consumer_name=f"real-anti-fraud-agent4-{uuid4().hex}",
        ),
    ]
    for consumer in consumers:
        await consumer._r()
    consumer_tasks = [asyncio.create_task(consumer.start()) for consumer in consumers]

    skill_path = ROOT / "backend" / "skills" / "anti_fraud_video.yaml"
    skill_yaml_text = skill_path.read_text(encoding="utf-8")
    skill_yaml = yaml.safe_load(skill_yaml_text)

    user_id = uuid4()
    conv_id = uuid4()
    task_id = None
    result: dict[str, object] = {}

    async with SessionLocal() as session:
        try:
            user = User(
                id=user_id,
                phone=f"135{str(user_id.int)[-8:]}",
                nickname="real-anti-fraud-live",
                plan="team",
            )
            session.add(user)

            existing_skill = (
                await session.execute(select(Skill).where(Skill.skill_id == "anti_fraud_video"))
            ).scalar_one_or_none()
            if existing_skill is None:
                skill = Skill(
                    id=uuid4(),
                    skill_id="anti_fraud_video",
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
            conv = Conversation(
                id=conv_id,
                user_id=user_id,
                name="反诈视频真实全链路测试群",
                mode="group",
                work_mode="auto",
                skill_id=skill.id,
                brief={
                    "字段": {
                        "年份": 2026,
                        "骗局类型": "电信诈骗",
                        "受众": "城市老人",
                        "时长": "60s",
                        "开头钩子": "一个电话，可能掏空老人半辈子的积蓄。",
                    },
                },
            )
            session.add(conv)
            await session.commit()

            runner = make_runner(session)
            messages_api.make_runner = lambda _session: runner

            response = await send_message(
                conv_id,
                SendMessageRequest(
                    content=(
                        "请直接开干，帮我做一个60秒反诈视频，主题是2026年电信诈骗，"
                        "给城市老人看，要求有真实案例调研、脚本、配图、配乐和最终视频。"
                    )
                ),
                session,
            )
            if response.decision != "task_started":
                raise RuntimeError(f"send_message did not start task: {response.model_dump()}")

            task_id = response.payload["task_id"]
            approved: list[str] = []

            for _ in range(12):
                gates = (
                    await session.execute(
                        select(HITLGate)
                        .where(HITLGate.task_id == task_id, HITLGate.closed_at.is_(None))
                        .order_by(HITLGate.opened_at)
                    )
                ).scalars().all()
                if gates:
                    gate = gates[0]
                    approved.append(gate.step_id)
                    await runner.resolve_hitl(
                        gate.id,
                        resolution="approved",
                        user_choice={"approved_by": "real_live_script", "step_id": gate.step_id},
                    )
                    continue

                task = await session.get(Task, task_id)
                if task and task.status in {"completed", "failed", "cancelled"}:
                    break
                await asyncio.sleep(5)

            task = await session.get(Task, task_id)
            steps = (
                await session.execute(select(TaskStep).where(TaskStep.task_id == task_id))
            ).scalars().all()
            gates = (
                await session.execute(select(HITLGate).where(HITLGate.task_id == task_id))
            ).scalars().all()

            result = {
                "task_id": str(task_id),
                "task_status": task.status if task else None,
                "approved_gates": approved,
                "steps": {
                    step.step_id: {
                        "status": step.status,
                        "output_artifact_id": str(step.output_artifact_id)
                        if step.output_artifact_id
                        else None,
                        "metadata": step.extra_metadata,
                        "error": step.error_detail,
                    }
                    for step in steps
                },
                "gates": {gate.step_id: gate.resolution for gate in gates},
            }
        finally:
            for consumer in consumers:
                consumer.stop()
            for handle in consumer_tasks:
                handle.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await handle
            await close_redis()
            await engine.dispose()

    if result.get("task_status") != "completed":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    from app.db import SessionLocal as ArtifactSessionLocal
    from app.models.artifact import Artifact

    video_step = result["steps"]["video_compose"]  # type: ignore[index]
    artifact_id = video_step["output_artifact_id"]  # type: ignore[index]
    async with ArtifactSessionLocal() as session:
        artifact = await session.get(Artifact, artifact_id)
        if artifact is None:
            raise RuntimeError(f"video artifact not found: {artifact_id}")
        video_ref = artifact.reference
    bucket, key = parse_oss_ref(str(video_ref))
    head = s3_client().head_object(Bucket=bucket, Key=key)
    result["video_object"] = {
        "bucket": bucket,
        "key": key,
        "size": head.get("ContentLength"),
        "content_type": head.get("ContentType"),
        "minio_browser": f"http://localhost:9001/browser/{bucket}/{key}",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
