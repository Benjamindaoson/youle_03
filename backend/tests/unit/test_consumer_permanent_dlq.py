"""Agent consumer 异常粒度:解析 / 边界错(永久错)直接 DLQ,不消耗重试预算。"""

from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest
from agents._common import consumer as consumer_mod
from agents._common.consumer import AgentConsumer
from agents._common.protocol import AgentResult, AgentTask


@pytest.fixture
def fake_redis(monkeypatch):
    redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(
        "agents._common.consumer.aioredis.from_url", lambda *a, **k: redis
    )
    return redis


async def _ok_handler(task: AgentTask) -> AgentResult:
    return AgentResult(task_id=task.task_id, step_id=task.step_id, status="completed")


@pytest.mark.asyncio
async def test_invalid_json_goes_dlq_immediately(monkeypatch, fake_redis) -> None:
    """坏 JSON → 永久错,直接 DLQ,不耗重试预算。"""
    monkeypatch.setattr(consumer_mod, "MAX_RETRIES", 5)  # 大重试预算,看是否被消耗
    monkeypatch.setattr(consumer_mod, "RETRY_BASE_SLEEP", 0.0)

    consumer = AgentConsumer(
        agent_id="agent_1", handlers={"web_search": _ok_handler}, consumer_name="t-1"
    )
    redis = await consumer._r()
    await redis.xadd(consumer.queue, {"data": "{not json"})

    resp = await redis.xreadgroup(
        consumer.group, "t-1", streams={consumer.queue: ">"}, count=1, block=100
    )
    for _stream, messages in resp or []:
        for mid, fields in messages:
            await consumer._dispatch(redis, mid, fields)

    # 直接 DLQ,不应 retry
    dlq_len = await redis.xlen("agent_dlq:agent_1")
    assert dlq_len == 1
    # queue 没 retry 入队(_attempt = 0 直接 DLQ)
    queue_after = await redis.xlen(consumer.queue)
    assert queue_after == 1  # 原始消息仍在(我们直接 ack 它)— 检查 DLQ 标记
    dlq_msgs = await redis.xrange("agent_dlq:agent_1")
    assert dlq_msgs[0][1].get("type") == "permanent_error"


@pytest.mark.asyncio
async def test_unknown_task_type_goes_dlq_immediately(monkeypatch, fake_redis) -> None:
    """未知 task_type → BoundaryViolation → 永久错直接 DLQ。"""
    monkeypatch.setattr(consumer_mod, "MAX_RETRIES", 5)
    monkeypatch.setattr(consumer_mod, "RETRY_BASE_SLEEP", 0.0)

    consumer = AgentConsumer(
        agent_id="agent_1", handlers={"web_search": _ok_handler}, consumer_name="t-2"
    )
    redis = await consumer._r()
    bad_task = AgentTask(
        task_id=__import__("uuid").uuid4(),
        step_id="x",
        agent_id="agent_1",
        task_type="ghost_task",  # 不在 boundary 里
        user_id=__import__("uuid").uuid4(),
        conversation_id=__import__("uuid").uuid4(),
    )
    await redis.xadd(consumer.queue, {"data": bad_task.model_dump_json()})

    resp = await redis.xreadgroup(
        consumer.group, "t-2", streams={consumer.queue: ">"}, count=1, block=100
    )
    for _stream, messages in resp or []:
        for mid, fields in messages:
            await consumer._dispatch(redis, mid, fields)

    dlq_msgs = await redis.xrange("agent_dlq:agent_1")
    assert len(dlq_msgs) == 1
    assert dlq_msgs[0][1].get("type") == "permanent_error"


@pytest.mark.asyncio
async def test_runtime_error_still_retries(monkeypatch, fake_redis) -> None:
    """handler 抛运行时错 → 走重试(不立即 DLQ),与永久错区分。"""
    monkeypatch.setattr(consumer_mod, "MAX_RETRIES", 2)
    monkeypatch.setattr(consumer_mod, "RETRY_BASE_SLEEP", 0.0)

    async def _bad(task: AgentTask) -> AgentResult:
        raise RuntimeError("transient")

    consumer = AgentConsumer(
        agent_id="agent_1", handlers={"web_search": _bad}, consumer_name="t-3"
    )
    redis = await consumer._r()
    from uuid import uuid4

    task = AgentTask(
        task_id=uuid4(), step_id="s", agent_id="agent_1", task_type="web_search",
        user_id=uuid4(), conversation_id=uuid4(),
    )
    await redis.xadd(consumer.queue, {"data": task.model_dump_json()})

    resp = await redis.xreadgroup(
        consumer.group, "t-3", streams={consumer.queue: ">"}, count=1, block=100
    )
    for _stream, messages in resp or []:
        for mid, fields in messages:
            await consumer._dispatch(redis, mid, fields)

    # 应当重试入队(_attempt=1),不应直接 DLQ
    dlq_now = await redis.xlen("agent_dlq:agent_1")
    assert dlq_now == 0  # 第一次失败后还有 retry 预算
    # 队列里应当有重试消息
    msgs = await redis.xrange(consumer.queue)
    retry_msgs = [m for m in msgs if m[1].get("_attempt") == "1"]
    assert len(retry_msgs) == 1
