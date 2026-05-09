"""向 `agent_results:{task_id}` 写入与编排层一致的 AgentResult JSON。"""

from __future__ import annotations

from uuid import UUID

import structlog

from app.redis_client import get_redis
from app.schemas.agent import AgentResult

log = structlog.get_logger(__name__)


async def publish_agent_result_to_stream(result: AgentResult) -> None:
    redis = await get_redis()
    key = f"agent_results:{result.task_id}"
    await redis.xadd(key, {"data": result.model_dump_json()})


async def cleanup_task_redis(task_id: UUID | str) -> None:
    """任务完成/失败后清理 Redis 中的临时 key,防止跨存储状态分叉。

    幂等操作(Redis DEL/UNLINK 对不存在 key 是无害的),安全重试。
    调用方应 try/except 并仅记录 warning,不阻塞主流程。
    """
    tid = str(task_id)
    redis = await get_redis()
    keys = [
        f"agent_results:{tid}",   # 结果流(Worker 读完后应清理)
        f"agent_cancel:{tid}",    # 取消标志
        f"result_cursor:{tid}:*", # result_waiter 的 read cursor(若有)
    ]
    # 先直接删有确定 key 的,再用 SCAN 清理 cursor 通配符
    await redis.delete(f"agent_results:{tid}", f"agent_cancel:{tid}")
    # 用 SCAN 处理 cursor key(可能按 step_id 派生)
    cursor = 0
    pattern = f"result_cursor:{tid}:*"
    while True:
        cursor, found = await redis.scan(cursor, match=pattern, count=100)
        if found:
            await redis.delete(*found)
        if cursor == 0:
            break
    log.info("agent_result_stream.redis_cleaned", task_id=tid)
