"""image_generate 产物 normalize 单测 — 4 类输入(oss/data_uri/URL/fallback)。"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from agents.image_agent.handlers.extras import _normalize_image_artifact


@pytest.mark.asyncio
async def test_oss_ref_passthrough() -> None:
    """resp.content 已是 oss:// → 直接用。"""
    ref, via = await _normalize_image_artifact(
        resp_content="oss://bucket/path/x.png",
        task_id=str(uuid4()),
        step_id="s",
    )
    assert ref == "oss://bucket/path/x.png"
    assert via == "oss_ref"


@pytest.mark.asyncio
async def test_data_uri_decoded_and_uploaded() -> None:
    """data:image/png;base64,xxx → decode + 写 OSS。"""
    fake_oss = "oss://test-bucket/artifacts/T/s.png"
    payload = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100).decode()
    data_uri = f"data:image/png;base64,{payload}"

    with patch(
        "agents._common.oss_writer.put_bytes",
        AsyncMock(return_value=fake_oss),
    ) as put_bytes:
        ref, via = await _normalize_image_artifact(
            resp_content=data_uri, task_id="T", step_id="s"
        )
    assert ref == fake_oss
    assert via == "data_uri"
    put_bytes.assert_awaited_once()
    # 验证 content_type 是 image/png
    call_kwargs = put_bytes.await_args.kwargs
    assert call_kwargs["content_type"] == "image/png"


@pytest.mark.asyncio
async def test_data_uri_decode_failure_falls_back() -> None:
    """损坏 base64 → fallback ref(不 crash)。"""
    bad_uri = "data:image/png;base64,!!!not_valid_base64@@@"
    ref, via = await _normalize_image_artifact(
        resp_content=bad_uri, task_id="T", step_id="s"
    )
    assert ref == "oss://artifacts/T/s.png"
    assert via in ("data_uri_decode_failed", "fallback")


@pytest.mark.asyncio
async def test_http_url_downloads_and_uploads() -> None:
    """http URL → httpx 下载 → 写 OSS。"""
    fake_oss = "oss://bucket/artifacts/T/s.png"

    class FakeResp:
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def get(self, url): return FakeResp()

    with patch(
        "agents._common.oss_writer.put_bytes",
        AsyncMock(return_value=fake_oss),
    ), patch("httpx.AsyncClient", lambda **kw: FakeClient()):
        ref, via = await _normalize_image_artifact(
            resp_content="https://example.com/img.png", task_id="T", step_id="s"
        )
    assert ref == fake_oss
    assert via == "downloaded_url"


@pytest.mark.asyncio
async def test_fallback_for_text_summary() -> None:
    """LLM 返回纯文本(LITELLM_MOCK 时)→ fallback ref。"""
    ref, via = await _normalize_image_artifact(
        resp_content="一张赛博朋克风格的咖啡杯图",
        task_id="T",
        step_id="s",
    )
    assert ref == "oss://artifacts/T/s.png"
    assert via == "fallback"


@pytest.mark.asyncio
async def test_empty_content_falls_back() -> None:
    ref, via = await _normalize_image_artifact(
        resp_content="", task_id="T", step_id="s"
    )
    assert ref == "oss://artifacts/T/s.png"
    assert via == "fallback"
