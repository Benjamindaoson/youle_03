"""Agent 1 extras handlers — V1.5 真实现单测(铁律 11 PM override)。

5 个 handler:structured_writing / summarization / analysis / translation / polish
- 都走 LiteLLM mock(LITELLM_MOCK=true)
- patch oss_writer.put_text / put_bytes 走纯内存
- 验证 status / artifact_type / metadata / error 分支
"""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

os.environ.setdefault("LITELLM_MOCK", "true")


@pytest.fixture(autouse=True)
def _patch_io(monkeypatch):
    async def fake_put_text(*, key, content, content_type="text/plain"):
        return f"oss://test/{key}"

    monkeypatch.setattr("agents._common.oss_writer.put_text", fake_put_text)
    # extras 模块在文件顶 import,要打到模块导入名
    monkeypatch.setattr("agents.text_agent.handlers.extras.put_text", fake_put_text)


def _make_task(task_type: str, **kw):
    from agents._common.protocol import AgentTask

    return AgentTask(
        task_id=uuid4(),
        step_id=f"s_{task_type}",
        agent_id="agent_1",
        task_type=task_type,
        user_id=uuid4(),
        conversation_id=uuid4(),
        **kw,
    )


# ─── structured_writing ───
@pytest.mark.asyncio
async def test_structured_writing_missing_prompt() -> None:
    from agents.text_agent.handlers.extras import structured_writing_handler

    task = _make_task("structured_writing", inputs={}, parameters={})
    r = await structured_writing_handler(task)
    assert r.status == "failed"
    assert (r.error_detail or {}).get("reason") == "missing_prompt"


@pytest.mark.asyncio
async def test_structured_writing_with_schema(monkeypatch) -> None:
    """schema_keys 必须落到 metadata。"""
    from agents._common.llm import LLMResponse
    from agents.text_agent.handlers import extras

    fake_resp = LLMResponse(
        {
            "choices": [{"message": {"content": json.dumps({"title": "t", "body": "b"})}}],
            "model": "deepseek-v4-flash",
            "response_cost": 0.001,
        }
    )
    monkeypatch.setattr(extras.llm, "complete", AsyncMock(return_value=fake_resp))

    task = _make_task(
        "structured_writing",
        inputs={"_prompt": "写一篇博客大纲"},
        parameters={"schema": {"title": "string", "body": "string"}},
    )
    r = await extras.structured_writing_handler(task)
    assert r.status == "completed"
    assert r.output.type == "json"
    assert r.output.extra_metadata["valid_json"] is True
    assert "title" in r.output.extra_metadata["schema_keys"]
    assert set(r.output.extra_metadata["fields"]) == {"title", "body"}


# ─── summarization ───
@pytest.mark.asyncio
async def test_summarization_extractive_style(monkeypatch) -> None:
    from agents._common.llm import LLMResponse
    from agents.text_agent.handlers import extras

    fake = LLMResponse(
        {
            "choices": [{"message": {"content": "摘要要点 1。要点 2。要点 3。"}}],
            "model": "qwen-flash",
        }
    )
    monkeypatch.setattr(extras.llm, "complete", AsyncMock(return_value=fake))

    long_text = "这是一段长文本。" * 50
    task = _make_task(
        "summarization",
        inputs={"_prompt": long_text},
        parameters={"style": "extractive"},
    )
    r = await extras.summarization_handler(task)
    assert r.status == "completed"
    assert r.output.type == "text"
    md = r.output.extra_metadata
    assert md["style"] == "extractive"
    assert md["input_chars"] == len(long_text)
    assert md["compression"] < 1.0


@pytest.mark.asyncio
async def test_summarization_missing_text() -> None:
    from agents.text_agent.handlers.extras import summarization_handler

    r = await summarization_handler(_make_task("summarization", inputs={}))
    assert r.status == "failed"
    assert (r.error_detail or {}).get("reason") == "missing_text"


# ─── analysis ───
@pytest.mark.asyncio
async def test_analysis_json_with_claims(monkeypatch) -> None:
    from agents._common.llm import LLMResponse
    from agents.text_agent.handlers import extras

    payload = {
        "claims": ["论点1", "论点2"],
        "evidence": [["事实A"], ["数据B"]],
        "conclusion": "综上...",
    }
    fake = LLMResponse(
        {"choices": [{"message": {"content": json.dumps(payload)}}], "model": "claude-haiku"}
    )
    monkeypatch.setattr(extras.llm, "complete", AsyncMock(return_value=fake))

    task = _make_task("analysis", inputs={"text": "材料 X"})
    r = await extras.analysis_handler(task)
    assert r.status == "completed"
    md = r.output.extra_metadata
    assert md["valid_json"] is True
    assert md["claims_count"] == 2


@pytest.mark.asyncio
async def test_analysis_invalid_json(monkeypatch) -> None:
    from agents._common.llm import LLMResponse
    from agents.text_agent.handlers import extras

    fake = LLMResponse(
        {"choices": [{"message": {"content": "not json at all"}}], "model": "x"}
    )
    monkeypatch.setattr(extras.llm, "complete", AsyncMock(return_value=fake))

    r = await extras.analysis_handler(_make_task("analysis", inputs={"_prompt": "X"}))
    assert r.status == "completed"
    assert r.output.extra_metadata["valid_json"] is False
    assert r.output.extra_metadata["claims_count"] == 0


# ─── translation ───
@pytest.mark.asyncio
async def test_translation_with_glossary(monkeypatch) -> None:
    from agents._common.llm import LLMResponse
    from agents.text_agent.handlers import extras

    fake = LLMResponse(
        {
            "choices": [{"message": {"content": "Hello, the AI Agent works."}}],
            "model": "qwen-max",
        }
    )
    monkeypatch.setattr(extras.llm, "complete", AsyncMock(return_value=fake))

    task = _make_task(
        "translation",
        inputs={"_prompt": "你好,这个 AI 智能体能用"},
        parameters={"direction": "zh2en", "glossary": {"智能体": "AI Agent"}},
    )
    r = await extras.translation_handler(task)
    assert r.status == "completed"
    md = r.output.extra_metadata
    assert md["direction"] == "zh2en"
    assert md["glossary_size"] == 1
    assert md["glossary_hits"] == 1  # AI Agent 命中


@pytest.mark.asyncio
async def test_translation_missing() -> None:
    from agents.text_agent.handlers.extras import translation_handler

    r = await translation_handler(_make_task("translation", inputs={}))
    assert r.status == "failed"


# ─── polish ───
@pytest.mark.asyncio
async def test_polish_concise_style(monkeypatch) -> None:
    from agents._common.llm import LLMResponse
    from agents.text_agent.handlers import extras

    fake = LLMResponse(
        {"choices": [{"message": {"content": "短文本。"}}], "model": "deepseek-flash"}
    )
    monkeypatch.setattr(extras.llm, "complete", AsyncMock(return_value=fake))

    task = _make_task(
        "polish",
        inputs={"_prompt": "这一段 文字 有些 啰嗦 需要 删冗余"},
        parameters={"style": "concise"},
    )
    r = await extras.polish_handler(task)
    assert r.status == "completed"
    md = r.output.extra_metadata
    assert md["style"] == "concise"
    assert md["ratio"] < 1.0  # concise 必须缩短


@pytest.mark.asyncio
async def test_polish_unknown_style_falls_to_fluent(monkeypatch) -> None:
    """未知 style → 走 fluent 默认 prompt(不应 KeyError)。"""
    from agents._common.llm import LLMResponse
    from agents.text_agent.handlers import extras

    fake = LLMResponse({"choices": [{"message": {"content": "抛光后的文本"}}], "model": "x"})
    monkeypatch.setattr(extras.llm, "complete", AsyncMock(return_value=fake))

    task = _make_task(
        "polish", inputs={"_prompt": "原文"}, parameters={"style": "nonexistent"}
    )
    r = await extras.polish_handler(task)
    assert r.status == "completed"


@pytest.mark.asyncio
async def test_polish_llm_error_returns_failed(monkeypatch) -> None:
    from agents.text_agent.handlers import extras

    async def boom(*a, **kw):
        raise RuntimeError("LiteLLM down")

    monkeypatch.setattr(extras.llm, "complete", boom)
    r = await extras.polish_handler(_make_task("polish", inputs={"_prompt": "X"}))
    assert r.status == "failed"
    assert (r.error_detail or {}).get("reason") == "llm_error"
