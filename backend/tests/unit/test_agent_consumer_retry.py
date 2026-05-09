"""Agent 队列消费器:重试 / DLQ / 心跳 单测。

不需要真 Redis — 用 fakeredis(已在 dev deps)。
"""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import fakeredis.aioredis as fakeredis
import pytest
from agents._common import consumer as consumer_mod
from agents._common.consumer import AgentConsumer
from agents._common.protocol import AgentResult, AgentTask


@pytest.fixture
def fake_redis(monkeypatch):
    redis = fakeredis.FakeRedis(decode_responses=True)
    # 让 AgentConsumer._r() 用 fakeredis
    monkeypatch.setattr(
        "agents._common.consumer.aioredis.from_url", lambda *a, **k: redis
    )
    return redis


def _build_task(task_type: str = "web_search") -> AgentTask:
    return AgentTask(
        task_id=uuid4(),
        step_id="s1",
        agent_id="agent_1",
        task_type=task_type,
        user_id=uuid4(),
        conversation_id=uuid4(),
        timeout_seconds=2,
    )


@pytest.mark.asyncio
async def test_dlq_after_max_retries(monkeypatch, fake_redis) -> None:
    """handler 永远抛错 → 重试 MAX_RETRIES 次后写 DLQ + 写 fail 回执。"""
    monkeypatch.setattr(consumer_mod, "MAX_RETRIES", 1)
    monkeypatch.setattr(consumer_mod, "RETRY_BASE_SLEEP", 0.0)

    async def _bad_handler(task: AgentTask) -> AgentResult:
        raise RuntimeError("boom")

    consumer = AgentConsumer(
        agent_id="agent_1",
        handlers={"web_search": _bad_handler},
        consumer_name="test-1",
    )

    redis = await consumer._r()
    task = _build_task()
    await redis.xadd(consumer.queue, {"data": task.model_dump_json()})

    # 跑两轮 (1 次原始 + 1 次重试 → 然后 DLQ)
    async def _run_once() -> None:
        resp = await redis.xreadgroup(
            consumer.group, "test-1", streams={consumer.queue: ">"}, count=1, block=100
        )
        for _stream, messages in resp or []:
            for msg_id, fields in messages:
                await consumer._dispatch(redis, msg_id, fields)

    await _run_once()  # 原始 → 重试入队
    await _run_once()  # 重试 → DLQ

    dlq_len = await redis.xlen("agent_dlq:agent_1")
    assert dlq_len >= 1

    # fail 回执应当落在 agent_results:<task_id>
    result_stream = f"agent_results:{task.task_id}"
    fail_len = await redis.xlen(result_stream)
    assert fail_len >= 1
    msgs = await redis.xrange(result_stream)
    found_failed = False
    for _mid, fields in msgs:
        data = json.loads(fields["data"])
        if data.get("status") == "failed":
            found_failed = True
            assert data["error_detail"]["type"] == "max_retries_exceeded"
    assert found_failed


@pytest.mark.asyncio
async def test_timeout_triggers_retry(monkeypatch, fake_redis) -> None:
    """handler 超时 → 走重试路径(不直接 DLQ)。"""
    monkeypatch.setattr(consumer_mod, "MAX_RETRIES", 2)
    monkeypatch.setattr(consumer_mod, "RETRY_BASE_SLEEP", 0.0)

    async def _slow_handler(task: AgentTask) -> AgentResult:
        await asyncio.sleep(100)  # 永远超时
        raise RuntimeError("unreachable")

    consumer = AgentConsumer(
        agent_id="agent_1",
        handlers={"web_search": _slow_handler},
        consumer_name="test-2",
    )

    redis = await consumer._r()
    # 用极小 timeout
    task = _build_task()
    task = task.model_copy(update={"timeout_seconds": 1})
    await redis.xadd(consumer.queue, {"data": task.model_dump_json()})

    resp = await redis.xreadgroup(
        consumer.group, "test-2", streams={consumer.queue: ">"}, count=1, block=100
    )
    for _stream, messages in resp or []:
        for msg_id, fields in messages:
            # _dispatch 会 wait_for(timeout=10) — 我们 patch 一下
            monkeypatch.setattr(
                "agents._common.consumer.asyncio.wait_for",
                lambda coro, timeout: asyncio.wait_for(coro, timeout=0.1),
            )
            await consumer._dispatch(redis, msg_id, fields)

    # 重试入队 → 队列里应当至少有一条新消息(_attempt=1)
    new_len = await redis.xlen(consumer.queue)
    # 原消息已 ack,重试加了 1 条
    assert new_len >= 1


@pytest.mark.asyncio
async def test_unknown_task_type_goes_dlq(monkeypatch, fake_redis) -> None:
    monkeypatch.setattr(consumer_mod, "MAX_RETRIES", 0)  # 立即 DLQ
    monkeypatch.setattr(consumer_mod, "RETRY_BASE_SLEEP", 0.0)

    consumer = AgentConsumer(
        agent_id="agent_1",
        handlers={},  # 空,任何 task_type 都没 handler
        consumer_name="test-3",
    )
    redis = await consumer._r()
    task = _build_task(task_type="web_search")
    await redis.xadd(consumer.queue, {"data": task.model_dump_json()})
    resp = await redis.xreadgroup(
        consumer.group, "test-3", streams={consumer.queue: ">"}, count=1, block=100
    )
    for _stream, messages in resp or []:
        for msg_id, fields in messages:
            await consumer._dispatch(redis, msg_id, fields)

    dlq_len = await redis.xlen("agent_dlq:agent_1")
    assert dlq_len == 1
