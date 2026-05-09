"""Agent 3(设计师)进程入口。

本文件只做装配:汇总 image_agent 的业务 handler、构造 AgentConsumer、启动事件循环。
任务调度、ReAct 兜底等运行时行为由 AgentConsumer 配合 persona 在内部完成。
"""

from __future__ import annotations

import asyncio
import logging

from agents._common.consumer import AgentConsumer
from agents._common.react_personas import get_persona
from agents.image_agent.handlers.batch_generate import batch_generate_handler
from agents.image_agent.handlers.extras import (
    bg_remove_handler,
    enhance_handler,
    image_describe_handler,
    image_edit_handler,
    image_generate_handler,
)
from agents.image_agent.handlers.image_compose import image_compose_handler
from agents.image_agent.handlers.image_download import image_download_handler
from agents.image_agent.handlers.image_quality_check import image_quality_check_handler
from agents.image_agent.handlers.style_extract import style_extract_handler

logger = logging.getLogger(__name__)

AGENT_ID = "agent_3"

# 同一 handler 服务多个 task type 的场景集中在这里,避免散落在 dict 里难以发现。
# XHS 系列图片生成共用 image_generate_handler。
_XHS_IMAGE_GENERATE_TASKS = (
    "xhs_cover_image",
    "xhs_slide_text_image",
    "xhs_product_image",
    "xhs_ambience_image",
    "xhs_series_image",
)


def _build_handlers() -> dict[str, object]:
    """构造 task_type -> handler 映射。

    handler 注册集中在此函数,新增/修改任务类型只改这里,启动逻辑保持稳定。
    """
    handlers: dict[str, object] = {
        # 基础图像处理
        "image_download": image_download_handler,
        "image_generate": image_generate_handler,
        "image_edit": image_edit_handler,
        "image_describe": image_describe_handler,
        "image_compose": image_compose_handler,
        "image_quality_check": image_quality_check_handler,
        # 批量与风格
        "batch_generate": batch_generate_handler,
        "style_extract": style_extract_handler,
        # 抠图:`background_remove` 是规范命名,`bg_remove` 是历史别名,待统一后下线
        "background_remove": bg_remove_handler,
        "bg_remove": bg_remove_handler,
        # 增强
        "enhance": enhance_handler,
        # 小红书业务标签复用通用 handler
        "xhs_local_edit_image": image_edit_handler,
    }
    for task_type in _XHS_IMAGE_GENERATE_TASKS:
        handlers[task_type] = image_generate_handler

    return handlers


async def main() -> None:
    handlers = _build_handlers()
    logger.info(
        "%s starting | handler_count=%d | task_types=%s",
        AGENT_ID,
        len(handlers),
        sorted(handlers.keys()),
    )

    consumer = AgentConsumer(
        agent_id=AGENT_ID,
        handlers=handlers,
        persona=get_persona(AGENT_ID),
    )

    try:
        await consumer.start()
    finally:
        logger.info("%s stopped", AGENT_ID)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("%s received shutdown signal", AGENT_ID)