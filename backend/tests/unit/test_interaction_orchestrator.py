"""互动编排器(铁律 22 第 8 子模块):should_emit_handoff 决策 + emit_and_persist_handoff 写库。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from agents.orchestrator_agent.interaction import (
    MAX_HANDOFFS_PER_TASK,
    emit_and_persist_handoff,
    should_emit_handoff,
)


# ─────────────────────────────────────────────────────────────────
# should_emit_handoff(纯函数,V1 克制策略)
# ─────────────────────────────────────────────────────────────────
def test_first_step_no_handoff() -> None:
    """第 1 个 step 没有 prev,不能交接。"""
    assert (
        should_emit_handoff(prev_agent=None, current_agent="agent_1", handoffs_so_far=0)
        is False
    )


def test_same_agent_no_handoff() -> None:
    """同 Agent 连续两步不演内部细节。"""
    assert (
        should_emit_handoff(
            prev_agent="agent_1", current_agent="agent_1", handoffs_so_far=0
        )
        is False
    )


def test_cross_agent_emits() -> None:
    assert (
        should_emit_handoff(
            prev_agent="agent_1", current_agent="agent_3", handoffs_so_far=0
        )
        is True
    )


def test_solemn_scenario_disabled() -> None:
    """金融/医疗/政务 关闭演戏(铁律 19)。"""
    for s in ("finance", "medical", "government"):
        assert (
            should_emit_handoff(
                prev_agent="agent_1",
                current_agent="agent_3",
                handoffs_so_far=0,
                scenario=s,
            )
            is False
        )


def test_max_handoffs_per_task_caps() -> None:
    """超过上限不再触发(防刷屏)。"""
    assert (
        should_emit_handoff(
            prev_agent="agent_1",
            current_agent="agent_3",
            handoffs_so_far=MAX_HANDOFFS_PER_TASK,
        )
        is False
    )


# ─────────────────────────────────────────────────────────────────
# emit_and_persist_handoff(LLM mock + DB mock + WS mock)
# ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_emit_and_persist_writes_message_and_publishes() -> None:
    fake_resp = MagicMock()
    fake_resp.content = "@设计师 调研给你了,挑 5 张图出来"

    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    publish = AsyncMock()
    with patch(
        "agents.orchestrator_agent.interaction.complete", AsyncMock(return_value=fake_resp)
    ), patch("agents.orchestrator_agent.interaction.ws_manager.publish", publish):
        msg = await emit_and_persist_handoff(
            session,
            conversation_id=uuid4(),
            user_id=uuid4(),
            from_agent="agent_1",
            to_agent="agent_3",
            summary="调研报告写完了",
        )

    assert msg is not None
    assert msg.role == "agent_1"
    assert msg.content == "@设计师 调研给你了,挑 5 张图出来"
    assert (msg.extra_metadata or {}).get("kind") == "interaction"
    assert (msg.extra_metadata or {}).get("from_agent") == "agent_1"
    assert (msg.extra_metadata or {}).get("to_agent") == "agent_3"
    session.add.assert_called_once()
    session.commit.assert_awaited()
    publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_emit_skips_solemn_scenario() -> None:
    """严肃场景:不调 LLM、不写库、不推 WS。"""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    publish = AsyncMock()
    llm = AsyncMock()
    with patch("agents.orchestrator_agent.interaction.complete", llm), patch(
        "agents.orchestrator_agent.interaction.ws_manager.publish", publish
    ):
        msg = await emit_and_persist_handoff(
            session,
            conversation_id=uuid4(),
            user_id=uuid4(),
            from_agent="agent_1",
            to_agent="agent_3",
            summary="x",
            scenario="finance",
        )
    assert msg is None
    llm.assert_not_called()
    session.add.assert_not_called()
    publish.assert_not_called()


@pytest.mark.asyncio
async def test_emit_returns_none_when_llm_returns_empty() -> None:
    """LLM 返回空字符串(网络/限速失败 graceful 降级):不写库。"""
    fake_resp = MagicMock()
    fake_resp.content = "   "
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    publish = AsyncMock()
    with patch(
        "agents.orchestrator_agent.interaction.complete", AsyncMock(return_value=fake_resp)
    ), patch("agents.orchestrator_agent.interaction.ws_manager.publish", publish):
        msg = await emit_and_persist_handoff(
            session,
            conversation_id=uuid4(),
            user_id=uuid4(),
            from_agent="agent_1",
            to_agent="agent_3",
            summary="x",
        )
    assert msg is None
    session.add.assert_not_called()
    publish.assert_not_called()


@pytest.mark.asyncio
async def test_emit_handles_llm_exception_gracefully() -> None:
    """LLM 抛异常 不阻断主流程:返回 None,不写 DB。"""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    publish = AsyncMock()
    with patch(
        "agents.orchestrator_agent.interaction.complete",
        AsyncMock(side_effect=RuntimeError("rate limit")),
    ), patch("agents.orchestrator_agent.interaction.ws_manager.publish", publish):
        msg = await emit_and_persist_handoff(
            session,
            conversation_id=uuid4(),
            user_id=uuid4(),
            from_agent="agent_1",
            to_agent="agent_3",
            summary="x",
        )
    assert msg is None
    session.add.assert_not_called()
