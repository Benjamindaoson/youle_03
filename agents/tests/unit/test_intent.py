from __future__ import annotations

import pytest

from agents.orchestrator_agent.intent import understand_intent


@pytest.mark.asyncio
async def test_explicit_short_video_fields_are_kept_in_mock_mode() -> None:
    intent = await understand_intent(
        user_message=(
            "制作一条短视频。主题：城市漫游；风格：治愈向；受众：都市白领；"
            "时长：60s；平台：多平台。"
        )
    )

    assert intent.intent_type == "task_request"
    assert intent.scenario == "short_video"
    assert intent.entities == {
        "主题": "城市漫游",
        "风格": "治愈向",
        "受众": "都市白领",
        "时长": "60s",
        "平台": "多平台",
    }


@pytest.mark.asyncio
async def test_explicit_fields_support_ascii_colons_and_newlines() -> None:
    intent = await understand_intent(
        user_message="制作短视频\n主题: 海边日落\n风格: 故事向\n受众: Z 世代"
    )

    assert intent.entities["主题"] == "海边日落"
    assert intent.entities["风格"] == "故事向"
    assert intent.entities["受众"] == "Z 世代"


@pytest.mark.asyncio
async def test_explicit_fields_cover_every_canonical_skill_input() -> None:
    intent = await understand_intent(
        user_message=(
            "制作内容。商品图：https://example.com/product.png；卖点：轻便耐用；"
            "风格基调：专业；字数：800；页数：6；风格关键词：极简"
        )
    )

    assert intent.entities == {
        "商品图": "https://example.com/product.png",
        "卖点": "轻便耐用",
        "风格基调": "专业",
        "字数": "800",
        "页数": "6",
        "风格关键词": "极简",
    }
