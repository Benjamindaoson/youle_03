"""One-shot adapter for Volcengine Ark Seedream image generation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

ARK_IMAGE_GENERATIONS_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"


class ArkSeedreamConfigurationError(RuntimeError):
    """Raised before network access when live Ark credentials are absent."""


class ArkSeedreamResponseError(RuntimeError):
    """Raised when Ark returns no usable image URL."""


@dataclass(frozen=True)
class SeedreamImageResult:
    url: str
    model: str

    @classmethod
    def from_response(cls, payload: dict[str, Any]) -> "SeedreamImageResult":
        data = payload.get("data") or []
        first = data[0] if isinstance(data, list) and data else {}
        url = first.get("url") if isinstance(first, dict) else None
        if not isinstance(url, str) or not url:
            raise ArkSeedreamResponseError("Ark Seedream response did not include an image URL")
        return cls(url=url, model=str(payload.get("model") or "unknown"))


async def generate_seedream_image(
    *,
    prompt: str,
    size: str,
    reference_images: list[str] | None = None,
) -> SeedreamImageResult:
    """Generate exactly one image: no retry, no fallback, no hidden spend."""
    api_key = os.getenv("ARK_API_KEY", "").strip()
    if not api_key:
        raise ArkSeedreamConfigurationError("ARK_API_KEY is required for ecommerce live images")

    payload: dict[str, Any] = {
        "model": os.getenv("ECOMMERCE_SEEDREAM_MODEL", "doubao-seedream-4-0-250828"),
        "prompt": prompt,
        "size": size,
        "response_format": "url",
        "sequential_image_generation": "disabled",
        "stream": False,
        "watermark": True,
    }
    if reference_images:
        payload["image"] = reference_images

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0)) as client:
        response = await client.post(
            ARK_IMAGE_GENERATIONS_URL,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
    return SeedreamImageResult.from_response(response.json())
