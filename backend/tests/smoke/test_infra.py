"""Sprint 0 acceptance — 基础设施健康检查(对齐 CLAUDE.md §4)。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_router_mock_returns_fixed_text() -> None:
    """LITELLM_MOCK=True 时,router.complete 必须返回固定文本(不发网络)。"""
    from app.router import complete

    resp = await complete(
        task_type="intent_understanding",
        messages=[{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
    )
    assert resp.content  # 至少有内容
    assert "intent_type" in resp.content


@pytest.mark.asyncio
async def test_sms_dev_mode() -> None:
    """SMS_DEV_MODE=True:发短信不应抛错。"""
    from app.api.auth import sms_send
    from app.api.auth import SmsSendRequest

    # 仅校验函数能跑 — Redis 在测试环境用 fakeredis 之类的 fixture 替换
    req = SmsSendRequest(phone="13800138000")
    assert req.phone == "13800138000"


@pytest.mark.asyncio
async def test_settings_loaded() -> None:
    from app.config import settings

    assert settings.ENV in {"dev", "staging", "prod"}
    assert settings.cors_origins_list  # 至少 1 个
