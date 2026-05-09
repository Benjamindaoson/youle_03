"""mcp-platform-publish — 抖音 / 小红书 / 微信 发布 API 集成。

V1.5 范围(铁律 11):V1 返回 not_available stub,前端可据此展示「即将上线」提示。
真实 API 集成将在 V1.5 Sprint 完成:
  - 抖音开放平台 video.upload + video.create
  - 小红书企业号 content.publish
  - 微信视频号 media.upload_attachment + feeds.publish
"""

from __future__ import annotations

import os
from typing import Any

import structlog

from mcp_servers._shared.http_app import make_app

log = structlog.get_logger(__name__)

_V15_MSG = "平台发布功能将在 V1.5 上线,敬请期待"
_ENV = os.getenv("APP_ENV", "dev")


def _stub_response(platform: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """V1 统一 stub 响应 — 不抛异常,让调用方优雅降级。"""
    log.info(
        "platform_publish.stub_called",
        platform=platform,
        env=_ENV,
        artifact_ref=arguments.get("artifact_ref", "")[:80],
    )
    return {
        "status": "not_available",
        "platform": platform,
        "reason": "v1_5_scope",
        "message": _V15_MSG,
        "artifact_ref": arguments.get("artifact_ref"),
    }


async def douyin_publish(arguments: dict[str, Any]) -> dict[str, Any]:
    """上传短视频到抖音开放平台并创建投稿。

    V1.5 参数预留:
      artifact_ref (str)  — OSS 视频地址
      title        (str)  — 视频标题
      cover_ref    (str)  — 封面图 OSS 地址(可选)
      tags         (list) — 话题标签列表(可选)
    """
    return _stub_response("douyin", arguments)


async def xhs_publish(arguments: dict[str, Any]) -> dict[str, Any]:
    """发布图文/视频到小红书企业号。

    V1.5 参数预留:
      artifact_ref (str)  — 视频或图集 OSS 地址
      title        (str)  — 笔记标题
      desc         (str)  — 正文描述
      images       (list) — 图片 OSS 地址列表(图文笔记)
      tags         (list) — 话题标签(可选)
    """
    return _stub_response("xhs", arguments)


async def wechat_publish(arguments: dict[str, Any]) -> dict[str, Any]:
    """发布视频到微信视频号。

    V1.5 参数预留:
      artifact_ref (str)  — 视频 OSS 地址
      title        (str)  — 视频标题
      thumb_ref    (str)  — 封面图(可选)
    """
    return _stub_response("wechat", arguments)


async def check_publish_status(arguments: dict[str, Any]) -> dict[str, Any]:
    """查询发布任务状态。

    V1.5 参数预留:
      publish_id (str) — 发布任务 ID
      platform   (str) — 平台名称
    """
    return _stub_response("status_check", arguments)


app = make_app(
    server_name="platform-publish",
    tools={
        "douyin_publish": douyin_publish,
        "xhs_publish": xhs_publish,
        "wechat_publish": wechat_publish,
        "check_publish_status": check_publish_status,
    },
)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "7007"))
    uvicorn.run(app, host="0.0.0.0", port=port)
