from __future__ import annotations

import json

import httpx
import pytest
import respx

from agents.image_agent.handlers.ark_seedream import (
    ARK_IMAGE_GENERATIONS_URL,
    ArkSeedreamConfigurationError,
    generate_seedream_image,
)


@pytest.mark.asyncio
@respx.mock
async def test_seedream_posts_one_native_generation_request(monkeypatch) -> None:
    monkeypatch.setenv("ARK_API_KEY", "ark-test-key")
    route = respx.post(ARK_IMAGE_GENERATIONS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "doubao-seedream-4-0-250828",
                "data": [{"url": "https://img.example/a.jpg", "size": "2K"}],
            },
        )
    )

    result = await generate_seedream_image(prompt="thermos", size="2K")

    assert result.url == "https://img.example/a.jpg"
    assert result.model == "doubao-seedream-4-0-250828"
    assert route.call_count == 1
    request_body = json.loads(route.calls[0].request.content)
    assert request_body["sequential_image_generation"] == "disabled"


@pytest.mark.asyncio
async def test_seedream_without_key_fails_before_network(monkeypatch) -> None:
    monkeypatch.delenv("ARK_API_KEY", raising=False)

    with pytest.raises(ArkSeedreamConfigurationError):
        await generate_seedream_image(prompt="thermos", size="2K")
