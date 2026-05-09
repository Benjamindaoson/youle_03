"""Agent 4 V1.5 真实现 handlers 单测(铁律 11 PM override)。

10 个 task_type:
- text_to_video / image_to_video / video_describe → LiteLLM + normalize
- video_extract_frames / audio_extract / video_cut / subtitle_generate /
  subtitle_add / bgm_add / transition_apply → 走 MCP server,工厂生成
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

os.environ.setdefault("LITELLM_MOCK", "true")


def _make_task(task_type: str, **kw):
    from agents._common.protocol import AgentTask

    return AgentTask(
        task_id=uuid4(),
        step_id=f"s_{task_type}",
        agent_id="agent_4",
        task_type=task_type,
        user_id=uuid4(),
        conversation_id=uuid4(),
        **kw,
    )


# ─── 注册表完整性 ───
def test_v15_real_handlers_registry_complete() -> None:
    from agents.av_agent.handlers.v15_real import V15_REAL_HANDLERS

    expected = {
        "text_to_video", "image_to_video", "video_describe",
        "video_extract_frames", "audio_extract", "video_cut",
        "subtitle_generate", "subtitle_add", "bgm_add", "transition_apply",
    }
    assert set(V15_REAL_HANDLERS.keys()) == expected
    # 每个值都是可调用 handler
    for h in V15_REAL_HANDLERS.values():
        assert callable(h)


# ─── text_to_video ───
@pytest.mark.asyncio
async def test_text_to_video_missing_prompt() -> None:
    from agents.av_agent.handlers.v15_real import text_to_video_handler

    r = await text_to_video_handler(_make_task("text_to_video", inputs={}))
    assert r.status == "failed"
    assert (r.error_detail or {}).get("reason") == "missing_prompt"


@pytest.mark.asyncio
async def test_text_to_video_normalize_renames_to_mp4(monkeypatch) -> None:
    """normalize 默认产 .png,handler 必须改写成 .mp4。"""
    from agents._common.llm import LLMResponse
    from agents.av_agent.handlers import v15_real

    fake = LLMResponse({"choices": [{"message": {"content": "https://x.com/v.mp4"}}], "model": "veo-3"})
    monkeypatch.setattr(v15_real.llm, "complete", AsyncMock(return_value=fake))

    async def fake_norm(*, resp_content, task_id, step_id):
        return f"oss://test/artifacts/{task_id}/{step_id}.png", "downloaded_url"

    monkeypatch.setattr(
        "agents.image_agent.handlers.extras._normalize_image_artifact", fake_norm
    )

    task = _make_task("text_to_video", inputs={"_prompt": "做一段 6s 反诈视频"})
    r = await v15_real.text_to_video_handler(task)
    assert r.status == "completed"
    assert r.output.type == "video"
    assert r.output.reference.endswith(".mp4")
    assert r.output.extra_metadata["normalized_via"] == "downloaded_url"


# ─── image_to_video ───
@pytest.mark.asyncio
async def test_image_to_video_missing_image_ref() -> None:
    from agents.av_agent.handlers.v15_real import image_to_video_handler

    r = await image_to_video_handler(_make_task("image_to_video", inputs={}))
    assert r.status == "failed"
    assert (r.error_detail or {}).get("reason") == "missing_image_ref"


@pytest.mark.asyncio
async def test_image_to_video_happy(monkeypatch) -> None:
    from agents._common.llm import LLMResponse
    from agents.av_agent.handlers import v15_real

    fake = LLMResponse(
        {"choices": [{"message": {"content": "oss://b/v.mp4"}}], "model": "seedance-2"}
    )
    monkeypatch.setattr(v15_real.llm, "complete", AsyncMock(return_value=fake))

    async def fake_norm(*, resp_content, task_id, step_id):
        return resp_content, "oss_ref"

    monkeypatch.setattr(
        "agents.image_agent.handlers.extras._normalize_image_artifact", fake_norm
    )

    task = _make_task(
        "image_to_video", inputs={"image_ref": "oss://b/img.png"}
    )
    r = await v15_real.image_to_video_handler(task)
    assert r.status == "completed"
    assert r.output.type == "video"


# ─── video_describe ───
@pytest.mark.asyncio
async def test_video_describe_missing() -> None:
    from agents.av_agent.handlers.v15_real import video_describe_handler

    r = await video_describe_handler(_make_task("video_describe", inputs={}))
    assert r.status == "failed"
    assert (r.error_detail or {}).get("reason") == "missing_video_ref"


@pytest.mark.asyncio
async def test_video_describe_happy(monkeypatch) -> None:
    from agents._common.llm import LLMResponse
    from agents.av_agent.handlers import v15_real

    async def fake_call_tool(*, server, tool, arguments):
        return {
            "frames": [{"oss_ref": "oss://t/f1.png"}, {"oss_ref": "oss://t/f2.png"}],
            "duration": 12.5,
        }

    monkeypatch.setattr(v15_real.mcp_client, "call_tool", fake_call_tool)

    fake = LLMResponse(
        {"choices": [{"message": {"content": "视频展示了一只猫"}}], "model": "claude-haiku"}
    )
    monkeypatch.setattr(v15_real.llm, "complete", AsyncMock(return_value=fake))

    async def fake_put_text(*, key, content, content_type="text/plain"):
        return f"oss://test/{key}"

    monkeypatch.setattr("agents._common.oss_writer.put_text", fake_put_text)

    task = _make_task(
        "video_describe", inputs={"video_ref": "oss://t/v.mp4"}, parameters={"n_frames": 2}
    )
    r = await v15_real.video_describe_handler(task)
    assert r.status == "completed"
    assert r.output.type == "text"
    assert r.output.extra_metadata["frames_used"] == 2
    assert r.output.extra_metadata["video_duration"] == 12.5


@pytest.mark.asyncio
async def test_video_describe_extract_failed_propagates(monkeypatch) -> None:
    from agents.av_agent.handlers import v15_real

    async def fake_call_tool(*, server, tool, arguments):
        return {"_failed": True, "error": "ffmpeg not found"}

    monkeypatch.setattr(v15_real.mcp_client, "call_tool", fake_call_tool)

    r = await v15_real.video_describe_handler(
        _make_task("video_describe", inputs={"video_ref": "oss://t/v.mp4"})
    )
    assert r.status == "failed"
    assert (r.error_detail or {}).get("reason") == "extract_frames_failed"


# ─── MCP-wrapped handlers (factory) ───
@pytest.mark.asyncio
async def test_video_cut_missing_ref() -> None:
    from agents.av_agent.handlers.v15_real import video_cut_handler

    r = await video_cut_handler(_make_task("video_cut", inputs={}, parameters={}))
    assert r.status == "failed"
    assert (r.error_detail or {}).get("reason") == "missing_args"
    assert "ref" in (r.error_detail or {}).get("missing", [])


@pytest.mark.asyncio
async def test_video_cut_happy(monkeypatch) -> None:
    from agents.av_agent.handlers import v15_real

    async def fake_call_tool(*, server, tool, arguments):
        assert server == "video_tools"
        assert tool == "video_cut"
        return {"oss_ref": "oss://t/cut.mp4", "duration": 5.0}

    monkeypatch.setattr(v15_real.mcp_client, "call_tool", fake_call_tool)

    task = _make_task(
        "video_cut",
        inputs={"ref": "oss://t/v.mp4"},
        parameters={"start": 0, "end": 5},
    )
    r = await v15_real.video_cut_handler(task)
    assert r.status == "completed"
    assert r.output.type == "video"
    assert r.output.reference == "oss://t/cut.mp4"
    assert r.output.extra_metadata["duration"] == 5.0


@pytest.mark.asyncio
async def test_audio_extract_accepts_video_ref_alias(monkeypatch) -> None:
    """factory 兼容 video_ref / oss_ref / url 多名作 'ref'。"""
    from agents.av_agent.handlers import v15_real

    async def fake_call_tool(*, server, tool, arguments):
        return {"oss_ref": "oss://t/a.mp3"}

    monkeypatch.setattr(v15_real.mcp_client, "call_tool", fake_call_tool)

    task = _make_task(
        "audio_extract", inputs={"video_ref": "oss://t/v.mp4"}
    )
    r = await v15_real.audio_extract_handler(task)
    assert r.status == "completed"
    assert r.output.type == "audio"


@pytest.mark.asyncio
async def test_subtitle_generate_no_required_keys_passes_through(monkeypatch) -> None:
    """subtitle_generate 无 required_keys,直接转交给 audio_tools.subtitle_generate。"""
    from agents.av_agent.handlers import v15_real

    async def fake_call_tool(*, server, tool, arguments):
        assert server == "audio_tools"
        return {
            "oss_ref": "oss://t/srt.json",
            "chunks": [{"start": 0, "end": 1, "text": "hi"}],
        }

    monkeypatch.setattr(v15_real.mcp_client, "call_tool", fake_call_tool)

    r = await v15_real.subtitle_generate_handler(
        _make_task("subtitle_generate", inputs={"audio_url": "oss://t/a.mp3"})
    )
    assert r.status == "completed"
    assert r.output.type == "subtitle"


@pytest.mark.asyncio
async def test_factory_handler_mcp_failure(monkeypatch) -> None:
    from agents.av_agent.handlers import v15_real

    async def fake_call_tool(*, server, tool, arguments):
        return {"_failed": True, "error": "moviepy crashed"}

    monkeypatch.setattr(v15_real.mcp_client, "call_tool", fake_call_tool)

    r = await v15_real.video_cut_handler(
        _make_task("video_cut", inputs={"ref": "oss://t/v.mp4"})
    )
    assert r.status == "failed"
    assert "video_cut_failed" in (r.error_detail or {}).get("reason", "")


@pytest.mark.asyncio
async def test_factory_handler_no_artifact(monkeypatch) -> None:
    """MCP 返回但没 oss_ref → no_artifact。"""
    from agents.av_agent.handlers import v15_real

    async def fake_call_tool(*, server, tool, arguments):
        return {"some_meta": "X"}  # 没 oss_ref

    monkeypatch.setattr(v15_real.mcp_client, "call_tool", fake_call_tool)

    r = await v15_real.bgm_add_handler(
        _make_task("bgm_add", inputs={"ref": "oss://t/v.mp4"})
    )
    assert r.status == "failed"
    assert (r.error_detail or {}).get("reason") == "no_artifact"
