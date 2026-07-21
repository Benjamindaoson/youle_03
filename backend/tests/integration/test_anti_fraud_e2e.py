"""端到端 happy-path:消息 → 主编排 → Skill 编译 → AgentTask 派活清单。

Sprint 3 acceptance:
> 端到端:用户消息 → 主编排 → Agent 派活 → 拿到产物(全 mock)

此测试不需要 db/redis 真起;直接调子模块串起。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from agents.orchestrator_agent.input_validator import validate_inputs
from agents.orchestrator_agent.task_compiler import compile_task

from app.services.skill_loader import load_skill_by_id


@pytest.mark.asyncio
async def test_anti_fraud_video_compile() -> None:
    skill = load_skill_by_id("anti_fraud_video")

    # 模拟用户已澄清的字段
    collected = {
        "年份": 2026,
        "骗局类型": "电信诈骗",
        "受众": "城市老人",
        "时长": "60s",
    }

    # 输入校验
    validation = validate_inputs(
        inputs_schema=skill["inputs_schema"], collected_fields=collected
    )
    assert validation.is_complete, f"missing: {validation.missing_fields}"

    # 编排
    task_id, steps, agent_tasks = compile_task(
        skill_yaml=skill,
        collected_fields=validation.filled_fields,
        user_id=uuid4(),
        conversation_id=uuid4(),
    )
    assert len(steps) == 5
    assert len(agent_tasks) == 5

    # ADR-001-rev 编号正确
    queue_map = {at.agent_id for at in agent_tasks}
    assert queue_map == {"agent_1", "agent_3", "agent_4"}  # 反诈视频不需要 agent_2

    # research step 没有 depends_on,是入口
    research = next(s for s in steps if s.step_id == "research")
    assert research.depends_on == []

    # video_compose 是 hero 终审,有 final_approval gate
    video = next(s for s in steps if s.step_id == "video_compose")
    assert video.hitl_gate is not None
    assert video.hitl_gate["type"] == "final_approval"


@pytest.mark.asyncio
async def test_ecommerce_detail_image_compile() -> None:
    skill = load_skill_by_id("ecommerce_detail_image")

    collected = {
        "商品图": "oss://uploads/sample.png",
        "卖点": "天然有机、无添加",
        "受众": "城市妈妈",
        "风格": "暖色家居",
    }
    validation = validate_inputs(
        inputs_schema=skill["inputs_schema"], collected_fields=collected
    )
    assert validation.is_complete

    task_id, steps, agent_tasks = compile_task(
        skill_yaml=skill,
        collected_fields=validation.filled_fields,
        user_id=uuid4(),
        conversation_id=uuid4(),
    )
    # 5 步:style_analysis / copy_writing / segment_images / long_concat / quality_check
    step_ids = [s.step_id for s in steps]
    assert step_ids == [
        "style_analysis",
        "copy_writing",
        "segment_images",
        "long_concat",
        "quality_check",
    ]
    # long_concat 是 Agent 2(文档专员)处理(ADR-001-rev)
    long_concat = next(s for s in steps if s.step_id == "long_concat")
    assert long_concat.agent_id == "agent_2"
