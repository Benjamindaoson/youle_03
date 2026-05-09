from __future__ import annotations

import asyncio
import contextlib
import importlib
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

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
os.environ["LITELLM_MOCK"] = "false"
os.environ["DEBUG"] = "true"
os.environ.setdefault("AGENT_HEARTBEAT_INTERVAL", "60")


@dataclass(frozen=True)
class FlowCase:
    agent_id: str
    task_type: str
    handler_path: str
    inputs: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    expected_status: str = "completed"
    run_to_finalize: bool = True
    timeout: int = 240


AGENT1_CASES = [
    FlowCase("agent_1", "web_search", "agents.text_agent.handlers.web_search.web_search_handler"),
    FlowCase("agent_1", "long_writing", "agents.text_agent.handlers.long_writing.long_writing_handler"),
    FlowCase("agent_1", "short_video_script", "agents.text_agent.handlers.long_writing.long_writing_handler"),
    FlowCase("agent_1", "short_writing", "agents.text_agent.handlers.short_writing.short_writing_handler"),
    FlowCase(
        "agent_1",
        "version_compare",
        "agents.text_agent.handlers.version_compare.version_compare_handler",
        parameters={"count": 2},
    ),
    *[
        FlowCase("agent_1", task_type, f"agents.text_agent.handlers.extras.{task_type}_handler")
        for task_type in ["structured_writing", "summarization", "analysis", "translation", "polish"]
    ],
]

AGENT2_CASES = [
    FlowCase(
        "agent_2",
        "image_concat_long",
        "agents.document_agent.handlers.image_concat_long.image_concat_long_handler",
        inputs={"images": ["oss://live-test/a.png", "oss://live-test/b.png"]},
    ),
    *[
        FlowCase(
            "agent_2",
            task_type,
            f"agents.document_agent.handlers.extras.{task_type}_handler",
            inputs={"source_ref": "oss://live-test/source.bin"},
        )
        for task_type in ["pptx_assemble", "xlsx_assemble", "docx_assemble", "pdf_extract", "pdf_ocr"]
    ],
]

AGENT3_CASES = [
    FlowCase(
        "agent_3",
        "image_download",
        "agents.image_agent.handlers.image_download.image_download_handler",
        inputs={"urls": ["https://example.com/a.jpg"]},
    ),
    FlowCase(
        "agent_3",
        "batch_generate",
        "agents.image_agent.handlers.batch_generate.batch_generate_handler",
        parameters={"image_specs": [{"prompt": "极简蓝色图标"}, {"prompt": "极简绿色图标"}]},
        timeout=600,
    ),
    FlowCase(
        "agent_3",
        "image_quality_check",
        "agents.image_agent.handlers.image_quality_check.image_quality_check_handler",
        inputs={"reference": "https://example.com/a.png"},
    ),
    FlowCase(
        "agent_3",
        "style_extract",
        "agents.image_agent.handlers.style_extract.style_extract_handler",
        inputs={"reference": "https://example.com/a.png"},
    ),
    FlowCase(
        "agent_3",
        "image_generate",
        "agents.image_agent.handlers.extras.image_generate_handler",
        inputs={"_prompt": "一张白底极简产品图"},
    ),
    FlowCase(
        "agent_3",
        "image_edit",
        "agents.image_agent.handlers.extras.image_edit_handler",
        inputs={
            "_prompt": "把背景改成白色",
            "image_ref": "https://upload.wikimedia.org/wikipedia/commons/7/70/Example.png",
        },
    ),
    FlowCase(
        "agent_3",
        "image_describe",
        "agents.image_agent.handlers.extras.image_describe_handler",
        inputs={
            "_prompt": "请用一句话描述图片",
            "image_ref": "https://upload.wikimedia.org/wikipedia/commons/7/70/Example.png",
        },
    ),
    FlowCase("agent_3", "background_remove", "agents.image_agent.handlers.extras.bg_remove_handler"),
    FlowCase("agent_3", "bg_remove", "agents.image_agent.handlers.extras.bg_remove_handler"),
    FlowCase("agent_3", "enhance", "agents.image_agent.handlers.extras.enhance_handler"),
]

AGENT4_STUBS = [
    "text_to_video",
    "image_to_video",
    "video_describe",
    "video_extract_frames",
    "audio_extract",
    "video_cut",
    "subtitle_generate",
    "subtitle_add",
    "bgm_add",
    "transition_apply",
]

AGENT4_CASES = [
    FlowCase(
        "agent_4",
        "audio_to_text",
        "agents.av_agent.handlers.audio_to_text.audio_to_text_handler",
        inputs={"audio_url": "https://example.com/audio.mp3"},
    ),
    FlowCase("agent_4", "bgm_select", "agents.av_agent.handlers.bgm_select.bgm_select_handler"),
    FlowCase(
        "agent_4",
        "tts_generate",
        "agents.av_agent.handlers.tts_generate.tts_generate_handler",
        inputs={"text": "你好，这是一次全链路测试。"},
    ),
    FlowCase(
        "agent_4",
        "video_compose",
        "agents.av_agent.handlers.video_compose.video_compose_handler",
        parameters={"duration_field": "5s"},
        expected_status="pending_external",
        run_to_finalize=False,
    ),
    *[
        FlowCase(
            "agent_4",
            task_type,
            f"agents.av_agent.handlers.v15_stubs.V15_STUBS.{task_type}",
            expected_status="failed",
        )
        for task_type in AGENT4_STUBS
    ],
]

FLOW_CASES = [*AGENT1_CASES, *AGENT2_CASES, *AGENT3_CASES, *AGENT4_CASES]


def _load_handler(path: str):
    if ".V15_STUBS." in path:
        module_name, task_type = path.split(".V15_STUBS.", 1)
        module = importlib.import_module(module_name)
        return module, module.V15_STUBS[task_type]
    module_name, func_name = path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return module, getattr(module, func_name)


def _patch_module_io(module, monkeypatch):
    async def fake_put_text(*, key, content, content_type="text/plain"):
        return f"oss://live-test/{key}"

    async def fake_put_json(*, key, payload):
        return f"oss://live-test/{key}"

    async def fake_put_bytes(*, key, data, content_type):
        return f"oss://live-test/{key}"

    import agents._common.oss_writer as oss_writer

    monkeypatch.setattr(oss_writer, "put_text", fake_put_text)
    monkeypatch.setattr(oss_writer, "put_json", fake_put_json)
    monkeypatch.setattr(oss_writer, "put_bytes", fake_put_bytes)
    for name, func in {
        "put_text": fake_put_text,
        "put_json": fake_put_json,
        "put_bytes": fake_put_bytes,
    }.items():
        if hasattr(module, name):
            monkeypatch.setattr(module, name, func)


def _patch_common_external_io(monkeypatch):
    async def fake_call_tool(*, server, tool, arguments):
        if (server, tool) == ("search", "web_search"):
            return {
                "results": [
                    {
                        "title": "live mocked search",
                        "url": "https://example.com",
                        "snippet": "mock search result for full flow",
                    }
                ]
            }
        if (server, tool) == ("image_tools", "download_batch"):
            return {"oss_ref": "oss://live-test/images/", "downloaded_count": 1, "rejected_count": 0}
        if (server, tool) == ("image_tools", "concat_long"):
            return {"oss_ref": "oss://live-test/long.png"}
        if server == "image_tools":
            return {"oss_ref": f"oss://live-test/{tool}.png", "tool": tool}
        if server == "document_tools":
            if tool in {"pdf_extract", "pdf_ocr"}:
                return {"text": "mock extracted text", "page_count": 1}
            return {"oss_ref": f"oss://live-test/{tool}.bin", "page_count": 3}
        return {}

    async def fake_emit(*, signal_type, payload):
        return None

    monkeypatch.setattr("agents._common.mcp_client.mcp_client.call_tool", fake_call_tool)
    monkeypatch.setattr("agents._common.flywheel_emitter.emit", fake_emit)


def _patch_bgm_select(module, monkeypatch):
    class FakeEngine:
        async def dispose(self):
            return None

    class FakeRows:
        def first(self):
            return None

        def fetchall(self):
            return []

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, *args, **kwargs):
            return FakeRows()

    class FakeSessionMaker:
        def __call__(self):
            return FakeSession()

    monkeypatch.setattr(module, "create_async_engine", lambda *args, **kwargs: FakeEngine())
    monkeypatch.setattr(module, "async_sessionmaker", lambda *args, **kwargs: FakeSessionMaker())


def _patch_video_compose(module, monkeypatch):
    class FakeWorkflow:
        id = "langgraph-redis-live-celery-id"

    monkeypatch.setattr(
        module,
        "video_compose_workflow",
        SimpleNamespace(delay=lambda payload: FakeWorkflow()),
    )


async def _run_case_through_langgraph_redis(case: FlowCase, monkeypatch):
    import agents._common.llm as llm
    from agents._common.consumer import AgentConsumer
    from agents.orchestrator_agent.langgraph_runner.compiler import build_state_graph
    from agents.orchestrator_agent.langgraph_runner.result_waiter import wait_for_step_result
    from agents.orchestrator_agent.langgraph_runner.state import make_initial_state
    from app.redis_client import close_redis
    from app.services.dispatcher import dispatch_task

    await close_redis()
    importlib.reload(llm)
    module, handler = _load_handler(case.handler_path)
    if case.task_type == "bgm_select":
        _patch_bgm_select(module, monkeypatch)
    if case.task_type == "video_compose":
        _patch_video_compose(module, monkeypatch)
    _patch_module_io(module, monkeypatch)
    _patch_common_external_io(monkeypatch)

    consumer = AgentConsumer(
        agent_id=case.agent_id,  # type: ignore[arg-type]
        handlers={case.task_type: handler},
        consumer_name=f"flow-{case.agent_id}-{case.task_type}-{uuid4().hex}",
    )
    await consumer._r()
    consumer_task = asyncio.create_task(consumer.start())

    task_id = uuid4()
    step_id = case.task_type
    inputs = case.inputs or {"_prompt": f"请用一句中文回复: {case.task_type} full flow live test"}
    skill_yaml = {
        "skill_id": f"live_{case.agent_id}_{case.task_type}",
        "version": "0.1",
        "workflow": [
            {
                "step_id": step_id,
                "agent": case.agent_id,
                "task_type": case.task_type,
                "timeout": case.timeout,
                "inputs": inputs,
                "parameters": case.parameters or {"max_tokens": 80},
            }
        ],
        "delivery": {"primary_artifact": step_id},
    }

    try:
        graph = build_state_graph(
            skill_yaml,
            dispatcher=dispatch_task,
            result_waiter=wait_for_step_result,
        ).compile()
        state = make_initial_state(
            task_id=task_id,
            user_id=uuid4(),
            conversation_id=uuid4(),
            skill_id=None,
            skill_version="0.1",
            skill_yaml=skill_yaml,
            collected_fields={},
        )
        if case.run_to_finalize:
            final_state = await asyncio.wait_for(graph.ainvoke(state), timeout=case.timeout + 60)
            step_result = final_state["step_results"][step_id]
            return final_state, step_result

        await dispatch_task(
            __import__("app.schemas.agent", fromlist=["AgentTask"]).AgentTask(
                task_id=task_id,
                step_id=step_id,
                agent_id=case.agent_id,
                task_type=case.task_type,
                user_id=uuid4(),
                conversation_id=uuid4(),
                inputs=inputs,
                parameters=case.parameters,
                timeout_seconds=case.timeout,
            )
        )
        result = await asyncio.wait_for(
            wait_for_step_result(str(task_id), step_id, case.timeout),
            timeout=case.timeout + 60,
        )
        return None, {
            "status": result.status,
            "agent_id": case.agent_id,
            "task_type": case.task_type,
            "artifact_ref": result.output.reference if result and result.output else None,
            "artifact_type": result.output.type if result and result.output else None,
            "model_used": result.model_used,
            "external_workflow_id": result.external_workflow_id,
            "error_detail": result.error_detail,
        }
    finally:
        consumer.stop()
        consumer_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await consumer_task
        await close_redis()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", [pytest.param(case, id=f"{case.agent_id}-{case.task_type}") for case in FLOW_CASES])
async def test_all_agent_task_flows_via_langgraph_redis_live(case: FlowCase, monkeypatch):
    final_state, step_result = await _run_case_through_langgraph_redis(case, monkeypatch)

    assert step_result["status"] == case.expected_status
    assert step_result["agent_id"] == case.agent_id
    assert step_result["task_type"] == case.task_type

    if case.expected_status == "completed":
        assert step_result["artifact_ref"]
        assert step_result["artifact_type"]
        assert final_state is not None
        assert final_state["final_status"] == "completed"
        assert final_state["primary_artifact_ref"] == step_result["artifact_ref"]
    elif case.expected_status == "failed":
        assert final_state is not None
        assert final_state["final_status"] == "failed"
        assert step_result["error_detail"]
    elif case.expected_status == "pending_external":
        assert step_result["external_workflow_id"]
