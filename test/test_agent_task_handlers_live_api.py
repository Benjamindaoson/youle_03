from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
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

pytestmark = pytest.mark.skipif(
    os.getenv("YOULE_RUN_LIVE_TESTS") != "1",
    reason="requires explicit YOULE_RUN_LIVE_TESTS=1 and live provider APIs",
)


@pytest.fixture(autouse=True)
def _patch_external_io(monkeypatch):
    async def fake_put_text(*, key, content, content_type="text/plain"):
        return f"oss://live-test/{key}"

    async def fake_put_json(*, key, payload):
        return f"oss://live-test/{key}"

    async def fake_put_bytes(*, key, data, content_type):
        return f"oss://live-test/{key}"

    async def fake_emit(*, signal_type, payload):
        return None

    async def fake_call_tool(*, server, tool, arguments):
        if (server, tool) == ("search", "web_search"):
            return {"results": [{"title": "live mocked search", "url": "https://example.com"}]}
        if (server, tool) == ("image_tools", "download_batch"):
            return {"oss_ref": "oss://live-test/images/", "downloaded_count": 1, "rejected_count": 0}
        if (server, tool) == ("image_tools", "concat_long"):
            return {"oss_ref": "oss://live-test/long.png"}
        if server == "image_tools":
            return {"oss_ref": f"oss://live-test/{tool}.png"}
        if server == "document_tools":
            if tool in {"pdf_extract", "pdf_ocr"}:
                return {"text": "mock extracted text", "page_count": 1}
            return {"oss_ref": f"oss://live-test/{tool}.bin"}
        return {}

    monkeypatch.setattr("agents._common.oss_writer.put_text", fake_put_text)
    monkeypatch.setattr("agents._common.oss_writer.put_json", fake_put_json)
    monkeypatch.setattr("agents._common.oss_writer.put_bytes", fake_put_bytes)
    monkeypatch.setattr("agents._common.mcp_client.mcp_client.call_tool", fake_call_tool)
    monkeypatch.setattr("agents._common.flywheel_emitter.emit", fake_emit)


def _reload_live_llm():
    import agents._common.llm as llm

    return importlib.reload(llm)


def _task(*, agent_id: str, task_type: str, inputs=None, parameters=None, routing_hints=None):
    from agents._common.protocol import AgentTask

    return AgentTask(
        task_id=uuid4(),
        step_id=task_type,
        agent_id=agent_id,
        task_type=task_type,
        user_id=uuid4(),
        conversation_id=uuid4(),
        inputs=inputs or {"_prompt": f"请用一句中文回复: {task_type} live test"},
        parameters=parameters or {"max_tokens": 80},
        routing_hints=routing_hints or {},
        timeout_seconds=180,
    )


def _load_handler(path: str):
    module_name, func_name = path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return module, getattr(module, func_name)


def _patch_bgm_select(module, monkeypatch):
    class FakeEngine:
        async def dispose(self):
            return None

    class FakeRows:
        def first(self):
            return None

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
        id = "live-api-test-celery-id"

    monkeypatch.setattr(
        module,
        "video_compose_workflow",
        SimpleNamespace(delay=lambda payload: FakeWorkflow()),
    )


TASK_CASES = [
    ("agents.text_agent.handlers.web_search.web_search_handler", "agent_1", "web_search", {}, {}, "completed"),
    ("agents.text_agent.handlers.long_writing.long_writing_handler", "agent_1", "long_writing", {}, {}, "completed"),
    (
        "agents.text_agent.handlers.long_writing.long_writing_handler",
        "agent_1",
        "short_video_script",
        {},
        {},
        "completed",
    ),
    ("agents.text_agent.handlers.short_writing.short_writing_handler", "agent_1", "short_writing", {}, {}, "completed"),
    (
        "agents.text_agent.handlers.version_compare.version_compare_handler",
        "agent_1",
        "version_compare",
        {},
        {"count": 2},
        "completed",
    ),
    *[
        (f"agents.text_agent.handlers.extras.{task_type}_handler", "agent_1", task_type, {}, {}, "completed")
        for task_type in ["structured_writing", "summarization", "analysis", "translation", "polish"]
    ],
    (
        "agents.document_agent.handlers.image_concat_long.image_concat_long_handler",
        "agent_2",
        "image_concat_long",
        {"images": ["oss://live-test/a.png", "oss://live-test/b.png"]},
        {},
        "completed",
    ),
    *[
        (
            f"agents.document_agent.handlers.extras.{task_type}_handler",
            "agent_2",
            task_type,
            {"source_ref": "oss://live-test/source.bin"},
            {},
            "completed",
        )
        for task_type in ["pptx_assemble", "xlsx_assemble", "docx_assemble", "pdf_extract", "pdf_ocr"]
    ],
    (
        "agents.image_agent.handlers.image_download.image_download_handler",
        "agent_3",
        "image_download",
        {"urls": ["https://example.com/a.jpg"]},
        {},
        "completed",
    ),
    (
        "agents.image_agent.handlers.batch_generate.batch_generate_handler",
        "agent_3",
        "batch_generate",
        {},
        {"image_specs": [{"prompt": "一张极简蓝色图标"}, {"prompt": "一张极简绿色图标"}]},
        "completed",
    ),
    (
        "agents.image_agent.handlers.image_quality_check.image_quality_check_handler",
        "agent_3",
        "image_quality_check",
        {"reference": "https://example.com/a.png"},
        {},
        "completed",
    ),
    (
        "agents.image_agent.handlers.style_extract.style_extract_handler",
        "agent_3",
        "style_extract",
        {"reference": "https://example.com/a.png"},
        {},
        "completed",
    ),
    (
        "agents.image_agent.handlers.extras.image_generate_handler",
        "agent_3",
        "image_generate",
        {"_prompt": "一张白底极简产品图"},
        {},
        "completed",
    ),
    (
        "agents.image_agent.handlers.extras.image_edit_handler",
        "agent_3",
        "image_edit",
        {"_prompt": "把背景改成白色", "image_ref": "https://upload.wikimedia.org/wikipedia/commons/7/70/Example.png"},
        {},
        "completed",
    ),
    (
        "agents.image_agent.handlers.extras.image_describe_handler",
        "agent_3",
        "image_describe",
        {"_prompt": "请描述图片", "image_ref": "https://upload.wikimedia.org/wikipedia/commons/7/70/Example.png"},
        {},
        "completed",
    ),
    *[
        ("agents.image_agent.handlers.extras.bg_remove_handler", "agent_3", task_type, {}, {}, "completed")
        for task_type in ["background_remove", "bg_remove"]
    ],
    ("agents.image_agent.handlers.extras.enhance_handler", "agent_3", "enhance", {}, {}, "completed"),
    (
        "agents.av_agent.handlers.audio_to_text.audio_to_text_handler",
        "agent_4",
        "audio_to_text",
        {"audio_url": "https://example.com/audio.mp3"},
        {},
        "completed",
    ),
    ("agents.av_agent.handlers.bgm_select.bgm_select_handler", "agent_4", "bgm_select", {}, {}, "completed"),
    (
        "agents.av_agent.handlers.tts_generate.tts_generate_handler",
        "agent_4",
        "tts_generate",
        {"text": "你好，这是一次真实 API 连通性测试。"},
        {},
        "completed",
    ),
    (
        "agents.av_agent.handlers.video_compose.video_compose_handler",
        "agent_4",
        "video_compose",
        {},
        {"duration_field": "5s"},
        "pending_external",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler_path,agent_id,task_type,inputs,parameters,expected_status",
    [pytest.param(*case, id=case[2]) for case in TASK_CASES],
)
async def test_agent_task_handler_with_real_llm_api(
    handler_path,
    agent_id,
    task_type,
    inputs,
    parameters,
    expected_status,
    monkeypatch,
):
    _reload_live_llm()
    module, handler = _load_handler(handler_path)
    if task_type == "bgm_select":
        _patch_bgm_select(module, monkeypatch)
    if task_type == "video_compose":
        _patch_video_compose(module, monkeypatch)

    result = await handler(
        _task(
            agent_id=agent_id,
            task_type=task_type,
            inputs=inputs,
            parameters=parameters,
        )
    )

    assert result.status == expected_status
