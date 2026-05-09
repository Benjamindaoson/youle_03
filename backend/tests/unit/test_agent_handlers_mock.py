"""Agent handler 烟雾测试(LITELLM_MOCK + 不需要真 OSS/MCP)。

我们用 monkeypatch 替换 _common 里的 IO 函数,让 handler 在没有真 docker 时也能跑。
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

os.environ.setdefault("LITELLM_MOCK", "true")


@pytest.fixture(autouse=True)
def _patch_agent_io(monkeypatch):
    """patch OSS writer + MCP client + redis emit,使 handler 可纯内存跑。"""
    async def fake_put_text(*, key, content, content_type="text/plain"):
        return f"oss://test/{key}"

    async def fake_put_json(*, key, payload):
        return f"oss://test/{key}"

    async def fake_put_bytes(*, key, data, content_type):
        return f"oss://test/{key}"

    async def fake_call_tool(*, server, tool, arguments):
        if (server, tool) == ("search", "web_search"):
            return {
                "results": [
                    {"title": "t1", "url": "https://x.com/1", "snippet": "...", "image_url": "https://x.com/1.jpg"}
                ]
            }
        if (server, tool) == ("image_tools", "download_batch"):
            return {"downloaded_count": 5, "rejected_count": 0, "image_refs": ["oss://test/i1.jpg"]}
        if (server, tool) == ("image_tools", "concat_long"):
            return {"oss_ref": "oss://test/long.png"}
        return {}

    async def fake_emit(*, signal_type, payload):
        return None

    monkeypatch.setattr("agents._common.oss_writer.put_text", fake_put_text)
    monkeypatch.setattr("agents._common.oss_writer.put_json", fake_put_json)
    monkeypatch.setattr("agents._common.oss_writer.put_bytes", fake_put_bytes)
    monkeypatch.setattr("agents._common.mcp_client.mcp_client.call_tool", fake_call_tool)
    monkeypatch.setattr("agents._common.flywheel_emitter.emit", fake_emit)


@pytest.mark.asyncio
async def test_agent1_web_search() -> None:
    from agents._common.protocol import AgentTask
    from agents.text_agent.handlers.web_search import web_search_handler

    task = AgentTask(
        task_id=uuid4(),
        step_id="research",
        agent_id="agent_1",
        task_type="web_search",
        user_id=uuid4(),
        conversation_id=uuid4(),
        inputs={"_prompt": "2026 年电信诈骗案例"},
        parameters={"max_results": 5},
    )
    result = await web_search_handler(task)
    assert result.status == "completed"
    assert result.output is not None
    assert result.output.type == "structured"


@pytest.mark.asyncio
async def test_agent1_long_writing() -> None:
    from agents._common.protocol import AgentTask
    from agents.text_agent.handlers.long_writing import long_writing_handler

    task = AgentTask(
        task_id=uuid4(),
        step_id="script",
        agent_id="agent_1",
        task_type="long_writing",
        user_id=uuid4(),
        conversation_id=uuid4(),
        inputs={"_prompt": "写一段反诈视频脚本"},
    )
    result = await long_writing_handler(task)
    assert result.status == "completed"
    assert result.output is not None
    assert result.output.type == "text"


@pytest.mark.asyncio
async def test_agent3_image_download() -> None:
    from agents._common.protocol import AgentTask
    from agents.image_agent.handlers.image_download import image_download_handler

    task = AgentTask(
        task_id=uuid4(),
        step_id="image_process",
        agent_id="agent_3",
        task_type="image_download",
        user_id=uuid4(),
        conversation_id=uuid4(),
        inputs={"urls": ["https://example.com/1.jpg", "https://example.com/2.jpg"]},
        parameters={"check_quality": True, "min_resolution": "1080p"},
    )
    result = await image_download_handler(task)
    assert result.status == "completed"
    assert result.output.extra_metadata["count"] == 5


@pytest.mark.asyncio
async def test_agent2_image_concat_long() -> None:
    from agents._common.protocol import AgentTask
    from agents.document_agent.handlers.image_concat_long import image_concat_long_handler

    task = AgentTask(
        task_id=uuid4(),
        step_id="long_concat",
        agent_id="agent_2",
        task_type="image_concat_long",
        user_id=uuid4(),
        conversation_id=uuid4(),
        inputs={"images": ["oss://test/a.png", "oss://test/b.png", "oss://test/c.png"]},
    )
    result = await image_concat_long_handler(task)
    assert result.status == "completed"
    assert result.output.type == "image"
    assert result.output.reference == "oss://test/long.png"


@pytest.mark.asyncio
async def test_agent4_tts_generate() -> None:
    from agents._common.protocol import AgentTask
    from agents.av_agent.handlers.tts_generate import tts_generate_handler

    task = AgentTask(
        task_id=uuid4(),
        step_id="tts",
        agent_id="agent_4",
        task_type="tts_generate",
        user_id=uuid4(),
        conversation_id=uuid4(),
        inputs={"text": "你好,这是反诈宣传"},
        parameters={"voice": "female_warm"},
    )
    result = await tts_generate_handler(task)
    assert result.status == "completed"
    assert result.output.type == "audio"
