"""信号 4:高满意度 + 流程偏离预置 → SKILL_DRAFTER → skill_drafts(创作者飞轮)。

V1 实现写入逻辑(创作者计划 V2 才放出来给用户审核 / 发布)。
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from uuid import UUID, uuid4

import redis.asyncio as aioredis
import structlog

from app.config.prompts import SKILL_DRAFTER_PROMPT
from app.db import SessionLocal
from app.models.skill_draft import SkillDraft
from app.router import complete

log = structlog.get_logger(__name__)


async def _process(payload: dict[str, Any]) -> None:
    task_id = payload.get("task_id")
    user_id = payload.get("user_id")
    trace = payload.get("trace") or []
    user_satisfaction = payload.get("user_satisfaction") or 0

    # 只有 4-5 分才触发草稿
    if user_satisfaction < 4:
        return

    user_msg = (
        f"用户 ID:{user_id}\n"
        f"任务 ID:{task_id}\n"
        f"满意度:{user_satisfaction}/5\n"
        f"执行轨迹(每步):\n{json.dumps(trace, ensure_ascii=False, indent=2)}"
    )

    try:
        resp = await complete(
            task_type="brief_update",
            messages=[
                {"role": "system", "content": SKILL_DRAFTER_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=1200,
        )
    except Exception as e:
        log.warning("flywheel.draft.llm_failed", err=str(e))
        return

    yaml_text = resp.content.strip()
    # 简单提取 name
    name = "Skill 草稿"
    for line in yaml_text.splitlines():
        if line.lstrip().startswith("name:"):
            name = line.split(":", 1)[1].strip().strip('"').strip("'") or name
            break

    async with SessionLocal() as session:
        draft = SkillDraft(
            id=uuid4(),
            user_id=UUID(user_id) if user_id else None,
            source_task_id=UUID(task_id) if task_id else None,
            draft_yaml=yaml_text,
            name=name[:100],
            status="draft",
        )
        session.add(draft)
        await session.commit()
        log.info("flywheel.draft.written", draft_id=str(draft.id), name=name)


async def main() -> None:
    redis = aioredis.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True
    )
    last_id = "$"
    while True:
        try:
            resp = await redis.xread(
                {"flywheel:signals": last_id}, block=5000, count=10
            )
        except Exception as e:
            log.warning("flywheel.draft.xread_failed", err=str(e))
            await asyncio.sleep(2)
            continue
        if not resp:
            continue
        for _stream, messages in resp:
            for msg_id, fields in messages:
                last_id = msg_id
                if fields.get("type") not in ("skill_drafter", "skill_draft"):
                    continue
                try:
                    payload = json.loads(fields.get("payload", "{}"))
                except json.JSONDecodeError:
                    continue
                await _process(payload)


if __name__ == "__main__":
    asyncio.run(main())
