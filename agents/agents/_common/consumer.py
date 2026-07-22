"""Redis Streams 消费循环 — 4 个 Agent 共用入口。

加固清单(铁律 12:失败 3 层兜底):
- **重试**:同一 msg_id 失败 ≤ MAX_RETRIES 次 → 退避后重新入队
- **DLQ**:超过 MAX_RETRIES → 写 `agent_dlq:<agent_id>` 并 ack 原消息
- **超时取消**:每个 handler 包 `asyncio.wait_for(timeout=task.timeout_seconds)`,有 hard cap
- **心跳**:常驻协程每 HEARTBEAT_INTERVAL 秒 set_status(working/idle)
- **优雅停机**:SIGTERM/SIGINT → 先停止读队列 → 等当前任务结束 → 退出

已知限制(后续优化):
- 重试通过 xadd + ack 实现,失去 PEL 可见性。中期应改为 XAUTOCLAIM + idle-time 退避。
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from agents._common.react_personas import ReactPersona

import redis.asyncio as aioredis
import structlog

from agents._common.boundary import assert_task_in_boundary
from agents._common.flywheel_emitter import emit as flywheel_emit
from agents._common.protocol import QUEUE_MAP, AgentId, AgentResult, AgentTask

log = structlog.get_logger(__name__)

HandlerType = Callable[[AgentTask], Awaitable[AgentResult]]
RedisFields = dict[str, str]  # decode_responses=True 下 Redis Streams fields 都是 str

# ---------------------------------------------------------------------------
# 配置(从 env 读,启动时固定)
# ---------------------------------------------------------------------------

MAX_RETRIES = int(os.getenv("AGENT_MAX_RETRIES", "2"))   # 重试 2 次,合计 3 次尝试
RETRY_BASE_SLEEP = float(os.getenv("AGENT_RETRY_BASE_SLEEP", "1.0"))
HEARTBEAT_INTERVAL = float(os.getenv("AGENT_HEARTBEAT_INTERVAL", "20"))
IDEMPOTENCY_DONE_TTL = int(os.getenv("AGENT_IDEMPOTENCY_DONE_TTL", "604800"))  # 7d
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
REDIS_READ_BLOCK_MS = 5000
REDIS_SOCKET_TIMEOUT = float(os.getenv("AGENT_REDIS_SOCKET_TIMEOUT", "10"))

# Hard cap 防御:即使 task 设了夸张的 timeout_seconds,也不能让 worker 槽位锁太久
MAX_TASK_TIMEOUT_SEC = int(os.getenv("AGENT_MAX_TASK_TIMEOUT", "1800"))   # 30 分钟
MIN_TASK_TIMEOUT_SEC = 10

# DLQ / 回执 stream 长度上限
DLQ_MAXLEN = 2000
RESULT_MAXLEN = 50  # 单 task 健康场景 1-3 条,含中间态最多 ~10 条;50 给足余量

# 错误信息在日志/DLQ 里的截断长度
_ERR_MAX = 500


class AgentConsumer:
    def __init__(
        self,
        *,
        agent_id: AgentId,
        handlers: dict[str, HandlerType] | None = None,
        persona: ReactPersona | None = None,
        consumer_name: str | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.handlers = handlers or {}
        self.persona = persona
        self.queue = QUEUE_MAP[agent_id]
        self.consumer_name = consumer_name or f"{agent_id}-{os.getpid()}"
        self.group = f"{agent_id}-group"

        self._redis: aioredis.Redis | None = None
        self._stop = asyncio.Event()

        # 串行消费下 _inflight ∈ {0, 1};未来若改并发,需把这套状态改成 asyncio.Semaphore + counter
        self._inflight: int = 0
        self._last_user_id: UUID | None = None
        self._busy: bool = False

        self._react_fallback = self._build_react_fallback(persona)

    @staticmethod
    def _build_react_fallback(persona: ReactPersona | None) -> HandlerType | None:
        """ReAct 兜底 handler:未注册的 task_type 会走它。"""
        if persona is None:
            return None
        from agents._common.react_runner import run_react_agent_task

        async def _fallback(task: AgentTask) -> AgentResult:
            return await run_react_agent_task(task, persona)

        return _fallback

    async def _r(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_timeout=REDIS_SOCKET_TIMEOUT,
            )
            try:
                await self._redis.xgroup_create(self.queue, self.group, id="$", mkstream=True)
            except aioredis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise
        return self._redis

    # ── 信号处理 ──
    def _install_signals(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self._stop.set)
            except NotImplementedError:
                # Windows 不支持 add_signal_handler — 静默跳过
                pass

    @asynccontextmanager
    async def _busy_state(self, task: AgentTask) -> AsyncIterator[None]:
        """统一管理 inflight / busy / last_user_id 状态,避免散落的 +=/-= 漏改。"""
        self._busy = True
        self._last_user_id = task.user_id
        self._inflight += 1
        try:
            yield
        finally:
            self._busy = False
            self._inflight -= 1

    # ── 主循环 ──
    async def start(self) -> None:
        log.info("agent.consumer.start", agent_id=self.agent_id, queue=self.queue)
        self._install_signals()
        redis = await self._r()

        heartbeat_task = asyncio.create_task(self._heartbeat_loop_resilient())
        try:
            while not self._stop.is_set():
                try:
                    resp = await redis.xreadgroup(
                        self.group,
                        self.consumer_name,
                        streams={self.queue: ">"},
                        count=1,
                        block=REDIS_READ_BLOCK_MS,
                    )
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log.warning("agent.consumer.read_error", err=str(e))
                    await asyncio.sleep(1)
                    continue
                if not resp:
                    # 防止空轮询独占 CPU(某些 redis client 在无消息时立即返回)
                    await asyncio.sleep(0)
                    continue
                for _stream, messages in resp:
                    for msg_id, fields in messages:
                        await self._dispatch(redis, msg_id, fields)
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass
            log.info("agent.consumer.stopped", agent_id=self.agent_id)

    async def _heartbeat_loop_resilient(self) -> None:
        """心跳协程:任何异常都不崩,确保 worker 存活信号持续。"""
        while not self._stop.is_set():
            try:
                await self._heartbeat_once()
            except Exception as e:
                # 心跳本身挂了不应影响主循环;但要 error 级别,触发监控
                log.error("agent.heartbeat.iteration_failed", err=str(e), exc_info=True)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=HEARTBEAT_INTERVAL)
            except asyncio.TimeoutError:
                continue

    async def _heartbeat_once(self) -> None:
        redis = await self._r()
        payload = {
            "agent_id": self.agent_id,
            "status": "working" if self._busy else "idle",
            "ts": datetime.now(UTC).isoformat(),
            "consumer": self.consumer_name,
            "user_id": str(self._last_user_id) if self._last_user_id else "",
        }
        await redis.xadd(
            "agent_heartbeats",
            payload,
            maxlen=1000,
            approximate=True,
        )

    # ── 单条消息派发 ──
    async def _dispatch(
        self, redis: aioredis.Redis, msg_id: str, fields: RedisFields
    ) -> None:
        """分层异常处理(粒度更细,避免脏数据反复重试):

        - **解析 / 边界错(永久错)**:JSON 错 / Pydantic validation / BoundaryViolation /
          unknown task_type → 不重试,直接 DLQ(retries 没意义,问题不会自愈)
        - **handler 超时**:`asyncio.wait_for` → 走重试(可能下次成功)
        - **handler 抛异常**:运行时错 → 走重试(可能下次成功)
        """
        from pydantic import ValidationError

        from agents._common.boundary import BoundaryViolation

        attempt = int(fields.get("_attempt", 0) or 0)

        # ── 阶段 1:解析 + 边界(永久错,不重试)──
        try:
            payload = json.loads(fields.get("data", "{}"))
            task = AgentTask.model_validate(payload)
            assert_task_in_boundary(self.agent_id, task)
            handler = self.handlers.get(task.task_type) or self._react_fallback
            if handler is None:
                raise BoundaryViolation(
                    f"no handler for task_type={task.task_type}"
                )
        except (json.JSONDecodeError, ValidationError, BoundaryViolation) as e:
            log.error(
                "agent.consumer.permanent_error",
                err_type=type(e).__name__,
                err=str(e),
                msg_id=msg_id,
            )
            await self._send_to_dlq(
                redis,
                msg_id,
                fields,
                attempt,
                error=f"{type(e).__name__}: {e}",
                permanent=True,
            )
            return

        # 幂等检查:同 idempotency_key 已完成 → 直接 ack 不重做
        idempo_key = (task.idempotency_key or "").strip()
        done_redis_key = f"agent:idempotent_done:{idempo_key}" if idempo_key else ""
        cached_result = await redis.get(done_redis_key) if idempo_key else None
        if cached_result:
            pl = redis.pipeline(transaction=True)
            pl.xadd(
                f"agent_results:{task.task_id}",
                {"data": cached_result},
                maxlen=RESULT_MAXLEN,
                approximate=True,
            )
            pl.xack(self.queue, self.group, msg_id)
            await pl.execute()
            log.info(
                "agent.consumer.idempotent_result_replayed",
                task_id=str(task.task_id),
                step_id=task.step_id,
                idempotency_key=idempo_key,
                msg_id=msg_id,
            )
            return

        # ── 阶段 2:运行 handler(超时 / 异常 → 重试)──
        # task.timeout_seconds 由调用方控制,需要 hard cap 防止恶意/误配置锁住 worker 槽
        effective_timeout = max(
            MIN_TASK_TIMEOUT_SEC,
            min(task.timeout_seconds, MAX_TASK_TIMEOUT_SEC),
        )
        if effective_timeout != task.timeout_seconds:
            log.warning(
                "agent.consumer.timeout_clamped",
                requested=task.timeout_seconds,
                effective=effective_timeout,
                task_id=str(task.task_id),
            )

        t0 = time.monotonic()
        try:
            async with self._busy_state(task):
                result = await asyncio.wait_for(
                    handler(task),
                    timeout=effective_timeout,
                )
        except asyncio.TimeoutError:
            await self._retry_or_dlq(
                redis, msg_id, fields, attempt,
                error=f"timeout_{effective_timeout}s",
            )
            return
        except Exception as e:
            log.exception(
                "agent.consumer.handler_error",
                err=str(e),
                attempt=attempt,
                task_id=str(task.task_id),
                step_id=task.step_id,
                trace_id=task.trace_id,
                orchestration_run_id=str(task.orchestration_run_id)
                if task.orchestration_run_id
                else None,
                idempotency_key=task.idempotency_key,
                dispatch_attempt=task.dispatch_attempt,
            )
            await self._retry_or_dlq(redis, msg_id, fields, attempt, error=str(e))
            return

        # ── 阶段 3:写回执 + ack(成功路径)──
        # 保留 handler 内部测的 duration(更精细),consumer 统计端到端
        handler_duration_ms = result.duration_ms
        consumer_duration_ms = int((time.monotonic() - t0) * 1000)
        result.duration_ms = consumer_duration_ms

        pl = redis.pipeline(transaction=True)
        pl.xadd(
            f"agent_results:{task.task_id}",
            {"data": result.model_dump_json()},
            maxlen=RESULT_MAXLEN,
            approximate=True,
        )
        if idempo_key:
            pl.setex(done_redis_key, IDEMPOTENCY_DONE_TTL, result.model_dump_json())
        await pl.execute()

        await redis.xack(self.queue, self.group, msg_id)
        log.info(
            "agent.consumer.completed",
            agent_id=self.agent_id,
            task_id=str(task.task_id),
            step_id=task.step_id,
            status=result.status,
            duration_ms=consumer_duration_ms,
            handler_duration_ms=handler_duration_ms,
            trace_id=task.trace_id,
            orchestration_run_id=str(task.orchestration_run_id)
            if task.orchestration_run_id
            else None,
            idempotency_key=task.idempotency_key,
            dispatch_attempt=task.dispatch_attempt,
        )

        # 飞轮信号 — 工作流轨迹(铁律 15)统一在 consumer 成功路径 emit,
        # 避免每个 handler 重复埋点;handler 层若需更细粒度信号,可额外 emit。
        await self._emit_trace_safe(task, result)

    async def _emit_trace_safe(self, task: AgentTask, result: AgentResult) -> None:
        try:
            await flywheel_emit(
                signal_type="trace",
                payload={
                    "task_id": str(task.task_id),
                    "step_id": task.step_id,
                    "agent_id": self.agent_id,
                    "task_type": task.task_type,
                    "status": result.status,
                    "duration_ms": result.duration_ms,
                    "model_used": result.model_used,
                    "cost_usd": result.cost_usd,
                    "trace_id": task.trace_id,
                    "orchestration_run_id": str(task.orchestration_run_id)
                    if task.orchestration_run_id
                    else None,
                    "idempotency_key": task.idempotency_key,
                    "dispatch_attempt": task.dispatch_attempt,
                },
            )
        except Exception as e:  # noqa: BLE001
            log.warning("agent.consumer.trace_emit_failed", err=str(e))

    async def _retry_or_dlq(
        self,
        redis: aioredis.Redis,
        msg_id: str,
        fields: RedisFields,
        attempt: int,
        *,
        error: str,
    ) -> None:
        """运行时错重试 ≤ MAX_RETRIES,否则进 DLQ。永久错走 _send_to_dlq(permanent=True)。

        当前实现通过 xadd + xack 重新入队,失去 PEL 可见性;中期应迁移到 XAUTOCLAIM。
        """
        if attempt < MAX_RETRIES:
            delay = RETRY_BASE_SLEEP * (2 ** attempt)
            new_fields = dict(fields)
            new_fields["_attempt"] = str(attempt + 1)
            new_fields["_last_error"] = error[:_ERR_MAX]
            try:
                await asyncio.sleep(delay)
                await redis.xadd(self.queue, new_fields)
                await redis.xack(self.queue, self.group, msg_id)
                log.info(
                    "agent.consumer.retried",
                    agent_id=self.agent_id,
                    msg_id=msg_id,
                    attempt=attempt + 1,
                    delay=delay,
                )
            except Exception as e:
                log.warning("agent.consumer.retry_failed", err=str(e))
            return

        # 超出重试 → DLQ
        await self._send_to_dlq(redis, msg_id, fields, attempt, error=error, permanent=False)

    async def _send_to_dlq(
        self,
        redis: aioredis.Redis,
        msg_id: str,
        fields: RedisFields,
        attempt: int,
        *,
        error: str,
        permanent: bool,
    ) -> None:
        """直接 DLQ + ack + 写 fail 回执。

        permanent=True:解析 / 边界错(永久错,不应重试)
        permanent=False:运行时错耗尽重试

        DLQ 写入失败是严重事件:消息没 ack,会被 PEL/XAUTOCLAIM 机制再次拉起,
        触发监控告警(error 级别),由人工介入。
        """
        payload = fields.get("data", "{}")
        task_id, step_id = self._extract_task_ids_safe(payload)
        failure_type = "permanent_error" if permanent else "max_retries_exceeded"

        # DLQ 写入(独立 try,失败要严重告警)
        try:
            await redis.xadd(
                f"agent_dlq:{self.agent_id}",
                {
                    "msg_id": msg_id,
                    "data": payload,
                    "error": error[:_ERR_MAX],
                    "attempts": str(attempt + 1),
                    "type": failure_type,
                    "ts": datetime.now(UTC).isoformat(),
                },
                maxlen=DLQ_MAXLEN,
                approximate=True,
            )
        except Exception as e:
            log.error(
                "agent.consumer.dlq_write_failed",
                agent_id=self.agent_id,
                msg_id=msg_id,
                err=str(e),
                exc_info=True,
            )
            # DLQ 写不进去就不要 ack,让消息留在 PEL 等下次拉起
            return

        # 通知 runner(可选,失败可降级)
        if task_id and step_id:
            try:
                fail_result = AgentResult(
                    task_id=UUID(task_id),
                    step_id=step_id,
                    status="failed",
                    error_detail={
                        "type": failure_type,
                        "attempts": attempt + 1,
                        "error": error[:_ERR_MAX],
                    },
                )
                await redis.xadd(
                    f"agent_results:{task_id}",
                    {"data": fail_result.model_dump_json()},
                    maxlen=RESULT_MAXLEN,
                    approximate=True,
                )
            except Exception as e:
                log.warning("agent.consumer.fail_result_skip", err=str(e))

        # ack 老消息
        try:
            await redis.xack(self.queue, self.group, msg_id)
        except Exception as e:
            log.warning("agent.consumer.dlq_ack_failed", err=str(e))

        log.error(
            "agent.consumer.dlq",
            agent_id=self.agent_id,
            msg_id=msg_id,
            attempts=attempt + 1,
            permanent=permanent,
            error=error,
        )

    @staticmethod
    def _extract_task_ids_safe(payload: str) -> tuple[str | None, str | None]:
        """从 raw payload 安全提取 task_id / step_id,失败返回 (None, None)。"""
        try:
            obj = json.loads(payload)
            if isinstance(obj, dict):
                return obj.get("task_id"), obj.get("step_id")
        except Exception:
            pass
        return None, None

    def stop(self) -> None:
        self._stop.set()
