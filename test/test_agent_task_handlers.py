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

os.environ["LITELLM_MOCK"] = "true"


@pytest.fixture(autouse=True)
def _patch_external_io(monkeypatch):
    async def fake_put_text(*, key, content, content_type="text/plain"):
        return f"oss://test/{key}"

    async def fake_put_json(*, key, payload):
        return f"oss://test/{key}"

    async def fake_put_bytes(*, key, data, content_type):
        return f"oss://test/{key}"

    async def fake_emit(*, signal_type, payload):
        return None

    async def fake_call_tool(*, server, tool, arguments):
        if (server, tool) == ("search", "web_search"):
            return {
                "results": [
                    {
                        "title": "mock result",
                        "url": "https://example.com/a",
                        "snippet": "ok",
                    }
                ]
            }
        if (server, tool) == ("image_tools", "download_batch"):
            return {
                "oss_ref": "oss://test/images/",
                "downloaded_count": 2,
                "rejected_count": 0,
            }
        if (server, tool) == ("image_tools", "concat_long"):
            return {"oss_ref": "oss://test/long.png"}
        if server == "image_tools":
            return {"oss_ref": f"oss://test/{tool}.png", "tool": tool}
        if server == "document_tools":
            if tool in {"pdf_extract", "pdf_ocr"}:
                return {"text": "extracted text", "page_count": 1}
            return {"oss_ref": f"oss://test/{tool}.bin", "page_count": 3}
        return {}

    monkeypatch.setattr("agents._common.oss_writer.put_text", fake_put_text)
    monkeypatch.setattr("agents._common.oss_writer.put_json", fake_put_json)
    monkeypatch.setattr("agents._common.oss_writer.put_bytes", fake_put_bytes)
    monkeypatch.setattr("agents._common.mcp_client.mcp_client.call_tool", fake_call_tool)
    monkeypatch.setattr("agents._common.flywheel_emitter.emit", fake_emit)


def _load_handler(path: str):
    module_name, func_name = path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return module, getattr(module, func_name)


def _task(*, agent_id: str, task_type: str, inputs=None, parameters=None):
    from agents._common.protocol import AgentTask

    return AgentTask(
        task_id=uuid4(),
        step_id=task_type,
        agent_id=agent_id,
        task_type=task_type,
        user_id=uuid4(),
        conversation_id=uuid4(),
        inputs=inputs or {"_prompt": f"run {task_type}"},
        parameters=parameters or {},
    )


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
        id = "celery-test-id"

    monkeypatch.setattr(
        module,
        "video_compose_workflow",
        SimpleNamespace(delay=lambda payload: FakeWorkflow()),
    )


TASK_CASES = [
    pytest.param(
        "agents.text_agent.handlers.web_search.web_search_handler",
        "agent_1",
        "web_search",
        {"_prompt": "search anti fraud"},
        {"max_results": 3},
        "completed",
        "structured",
        id="agent1-web_search",
    ),
    pytest.param(
        "agents.text_agent.handlers.long_writing.long_writing_handler",
        "agent_1",
        "long_writing",
        {"_prompt": "write a script"},
        {},
        "completed",
        "text",
        id="agent1-long_writing",
    ),
    pytest.param(
        "agents.text_agent.handlers.long_writing.long_writing_handler",
        "agent_1",
        "short_video_script",
        {"_prompt": "write a short video script"},
        {},
        "completed",
        "text",
        id="agent1-short_video_script",
    ),
    pytest.param(
        "agents.text_agent.handlers.short_writing.short_writing_handler",
        "agent_1",
        "short_writing",
        {"_prompt": "write title"},
        {},
        "completed",
        "text",
        id="agent1-short_writing",
    ),
    pytest.param(
        "agents.text_agent.handlers.version_compare.version_compare_handler",
        "agent_1",
        "version_compare",
        {"_prompt": "make variants"},
        {"count": 2},
        "completed",
        "structured",
        id="agent1-version_compare",
    ),
    *[
        pytest.param(
            f"agents.text_agent.handlers.extras.{task_type}_handler",
            "agent_1",
            task_type,
            {"_prompt": f"run {task_type}"},
            {},
            "completed",
            expected_type,
            id=f"agent1-{task_type}",
        )
        for task_type, expected_type in [
            ("structured_writing", "json"),
            ("summarization", "text"),
            ("analysis", "json"),
            ("translation", "text"),
            ("polish", "text"),
        ]
    ],
    pytest.param(
        "agents.document_agent.handlers.image_concat_long.image_concat_long_handler",
        "agent_2",
        "image_concat_long",
        {"images": ["oss://test/a.png", "oss://test/b.png"]},
        {},
        "completed",
        "image",
        id="agent2-image_concat_long",
    ),
    *[
        pytest.param(
            f"agents.document_agent.handlers.extras.{task_type}_handler",
            "agent_2",
            task_type,
            {"source_ref": "oss://test/source.bin"},
            {},
            "completed",
            expected_type,
            id=f"agent2-{task_type}",
        )
        for task_type, expected_type in [
            ("pptx_assemble", "document"),
            ("xlsx_assemble", "document"),
            ("docx_assemble", "document"),
            ("pdf_extract", "text"),
            ("pdf_ocr", "text"),
        ]
    ],
    pytest.param(
        "agents.image_agent.handlers.image_download.image_download_handler",
        "agent_3",
        "image_download",
        {"urls": ["https://example.com/a.jpg"]},
        {},
        "completed",
        "image_collection",
        id="agent3-image_download",
    ),
    pytest.param(
        "agents.image_agent.handlers.image_compose.image_compose_handler",
        "agent_3",
        "image_compose",
        {
            "image_ref": "oss://test/base.png",
            "layers": [
                {"type": "badge", "content": "96110", "position": "bottom-right"},
                {"type": "text", "content": "反诈提醒", "position": "top-left",
                 "style": {"font_size": 32, "color": [255, 255, 255], "bg_color": [220, 38, 38, 200]}},
            ],
        },
        {},
        "completed",
        "image",
        id="agent3-image_compose",
    ),
    pytest.param(
        "agents.image_agent.handlers.batch_generate.batch_generate_handler",
        "agent_3",
        "batch_generate",
        {},
        {"image_specs": [{"prompt": "a"}, {"prompt": "b"}]},
        "completed",
        "image_collection",
        id="agent3-batch_generate",
    ),
    pytest.param(
        "agents.image_agent.handlers.image_quality_check.image_quality_check_handler",
        "agent_3",
        "image_quality_check",
        {"reference": "oss://test/a.png"},
        {},
        "completed",
        "quality_report",
        id="agent3-image_quality_check",
    ),
    pytest.param(
        "agents.image_agent.handlers.style_extract.style_extract_handler",
        "agent_3",
        "style_extract",
        {"reference": "oss://test/a.png"},
        {},
        "completed",
        "structured",
        id="agent3-style_extract",
    ),
    *[
        pytest.param(
            handler,
            "agent_3",
            task_type,
            {"_prompt": "make image", "image_ref": "oss://test/a.png"},
            {},
            "completed",
            expected_type,
            id=f"agent3-{task_type}",
        )
        for handler, task_type, expected_type in [
            ("agents.image_agent.handlers.extras.image_generate_handler", "image_generate", "image"),
            ("agents.image_agent.handlers.extras.image_edit_handler", "image_edit", "image"),
            ("agents.image_agent.handlers.extras.image_describe_handler", "image_describe", "text"),
            ("agents.image_agent.handlers.extras.bg_remove_handler", "background_remove", "image"),
            ("agents.image_agent.handlers.extras.bg_remove_handler", "bg_remove", "image"),
            ("agents.image_agent.handlers.extras.enhance_handler", "enhance", "image"),
        ]
    ],
    pytest.param(
        "agents.av_agent.handlers.audio_to_text.audio_to_text_handler",
        "agent_4",
        "audio_to_text",
        {"audio_url": "oss://test/audio.mp3"},
        {},
        "completed",
        "text",
        id="agent4-audio_to_text",
    ),
    pytest.param(
        "agents.av_agent.handlers.bgm_select.bgm_select_handler",
        "agent_4",
        "bgm_select",
        {},
        {"mood": "neutral", "duration_field": "30s"},
        "completed",
        "audio",
        id="agent4-bgm_select",
    ),
    pytest.param(
        "agents.av_agent.handlers.tts_generate.tts_generate_handler",
        "agent_4",
        "tts_generate",
        {"text": "hello"},
        {},
        "completed",
        "audio",
        id="agent4-tts_generate",
    ),
    pytest.param(
        "agents.av_agent.handlers.video_compose.video_compose_handler",
        "agent_4",
        "video_compose",
        {},
        {"duration_field": "10s"},
        "pending_external",
        None,
        id="agent4-video_compose",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler_path,agent_id,task_type,inputs,parameters,expected_status,expected_type",
    TASK_CASES,
)
async def test_registered_agent_task_handler_completes(
    handler_path,
    agent_id,
    task_type,
    inputs,
    parameters,
    expected_status,
    expected_type,
    monkeypatch,
):
    module, handler = _load_handler(handler_path)
    if hasattr(module, "get_user_prefs"):
        async def fake_get_user_prefs(*args, **kwargs):
            return {}

        monkeypatch.setattr(module, "get_user_prefs", fake_get_user_prefs)
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
    if expected_type is not None:
        assert result.output is not None
        assert result.output.type == expected_type
