"""Agent 1 long_writing handler — LiteLLM 流式输出,产物落 OSS,chunk 实时推 Redis Stream。

流式策略:
- 每个 LLM chunk 立即写入 agent_results:stream:{task_id}(maxlen=500,approximate)
- Frontend 可通过 WebSocket 订阅该 stream 实现打字机效果
- 最终 status=completed 时写 done=1 的哨兵消息
- Redis 不可用时静默降级:不影响最终产物
"""

from __future__ import annotations

import asyncio
import os
import time
from uuid import uuid4

import structlog

from agents._common import llm
from agents._common.flywheel_emitter import emit
from agents._common.oss_writer import put_text
from agents._common.prompts import LONG_WRITING_SYSTEM
from agents._common.protocol import AgentResult, AgentTask, ArtifactRef

log = structlog.get_logger(__name__)

# 与 backend `app.services.agent_cancel.CANCEL_KEY_PREFIX` 对齐
_CANCEL_FLAG_PREFIX = "agent_cancel"
_CHUNK_CANCEL_POLL = max(1, int(os.getenv("LONG_WRITING_CANCEL_POLL_CHUNKS", "6")))

_redis: object = None  # aioredis.Redis | False | None


async def _task_cancel_requested(redis: object | None, task_id: object) -> bool:
    if redis is None:
        return False
    try:
        return bool(await redis.exists(f"{_CANCEL_FLAG_PREFIX}:{task_id}"))  # type: ignore[union-attr]
    except Exception as e:
        log.warning(
            "long_writing.cancel_poll_failed",
            task_id=str(task_id),
            err_type=type(e).__name__,
            err=str(e)[:200],
        )
        return False


async def _get_redis() -> object:
    global _redis
    if _redis is None:
        try:
            import redis.asyncio as aioredis
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            _redis = aioredis.from_url(redis_url, decode_responses=True)
        except Exception:
            _redis = False
    return _redis if _redis is not False else None


async def _push_chunk(stream_key: str, step_id: str, chunk: str, seq: int, redis: object) -> None:
    if redis is None:
        return
    try:
        await redis.xadd(  # type: ignore[union-attr]
            stream_key,
            {"step_id": step_id, "seq": str(seq), "chunk": chunk, "done": "0"},
            maxlen=500,
            approximate=True,
        )
    except Exception as e:
        log.debug("long_writing.stream_push_error", err=str(e))


async def long_writing_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()
    user_prompt = task.inputs.get("_prompt") or task.inputs.get("prompt", "")
    if not user_prompt:
        return AgentResult(
            task_id=task.task_id,
            step_id=task.step_id,
            status="failed",
            error_detail={"reason": "missing_prompt"},
        )

    redis = await _get_redis()
    stream_key = f"agent_results:stream:{task.task_id}"
    chunks: list[str] = []
    seq = 0
    user_cancelled = False

    try:
        async for chunk in llm.stream(
            task_type=task.task_type,
            messages=[
                {"role": "system", "content": LONG_WRITING_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            routing_hints=task.routing_hints,
            temperature=0.7,
        ):
            chunks.append(chunk)
            await _push_chunk(stream_key, task.step_id, chunk, seq, redis)
            seq += 1
            if seq % _CHUNK_CANCEL_POLL == 0 and await _task_cancel_requested(redis, task.task_id):
                user_cancelled = True
                log.info(
                    "long_writing.user_cancelled_mid_stream",
                    task_id=str(task.task_id),
                    step_id=task.step_id,
                    chunks=seq,
                )
                break
    except asyncio.CancelledError:
        user_cancelled = True
        log.info(
            "long_writing.async_cancelled",
            task_id=str(task.task_id),
            step_id=task.step_id,
            chunks=seq,
        )
        raise

    if user_cancelled:
        if redis:
            try:
                await redis.xadd(  # type: ignore[union-attr]
                    stream_key,
                    {
                        "step_id": task.step_id,
                        "seq": str(seq),
                        "chunk": "",
                        "done": "2",
                        "cancelled": "1",
                    },
                    maxlen=500,
                    approximate=True,
                )
            except Exception:
                pass
        return AgentResult(
            task_id=task.task_id,
            step_id=task.step_id,
            status="failed",
            error_detail={
                "reason": "user_cancelled",
                "streamed_chunks": seq,
            },
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    full_text = "".join(chunks)

    # Stream completion sentinel
    if redis:
        try:
            await redis.xadd(  # type: ignore[union-attr]
                stream_key,
                {"step_id": task.step_id, "seq": str(seq), "chunk": "", "done": "1"},
                maxlen=500,
                approximate=True,
            )
        except Exception:
            pass

    artifact_id = uuid4()
    oss_ref = await put_text(
        key=f"artifacts/{task.task_id}/{task.step_id}.txt", content=full_text
    )

    await emit(
        signal_type="trace",
        payload={
            "task_id": str(task.task_id),
            "step_id": task.step_id,
            "agent_id": "agent_1",
            "task_type": task.task_type,
            "char_count": len(full_text),
            "stream_chunks": seq,
        },
    )

    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="completed",
        output=ArtifactRef(
            artifact_id=artifact_id,
            type="text",
            reference=oss_ref,
            extra_metadata={"length": len(full_text), "streamed_chunks": seq},
        ),
        duration_ms=int((time.monotonic() - t0) * 1000),
    )
