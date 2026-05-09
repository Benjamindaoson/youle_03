"""情景记忆检索 — 从 `workflow_traces`(Qdrant)召回相似历史任务的 plan + outcome。

# 演化(C 阶段已落地)
S1:返回空列表 stub。
**C 阶段(本次)**:接通 `agents._common.qdrant_client`,实现 top-K 召回 +
摘要拼接进 Planner prompt。flag 默认关 — 启用前需确认 backend 已写
`workflow_traces` collection 且 schema 与 `EpisodePayload` 对齐。

# Graceful 设计
任何失败(flag off / Qdrant 挂 / collection 不存在 / 嵌入失败)→ 空列表 + 警告。
critic 一样的设计哲学:基础设施挂不能让主流程崩。

# ADR-011 alignment
schema 见 `agents._common.qdrant_client.EpisodePayload`。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import structlog

from agents._common.qdrant_client import (
    EpisodePayload,
    search_episodes as _qdrant_search_episodes,
)

log = structlog.get_logger(__name__)

EPISODE_RETRIEVAL_ENABLED = (
    os.getenv("ENABLE_EPISODE_RETRIEVAL", "false").lower() == "true"
)
DEFAULT_TOP_K = int(os.getenv("EPISODE_RETRIEVAL_TOP_K", "3"))
EPISODE_ONLY_SUCCESS = (
    os.getenv("EPISODE_RETRIEVAL_ONLY_SUCCESS", "true").lower() == "true"
)


@dataclass
class Episode:
    """一条历史任务摘要,送入 Planner 作为 few-shot 经验。"""

    task_id: str
    user_request: str
    plan_summary: str
    outcome: str  # "success" / "failed" / "partial"
    user_rating: float | None  # 0..1
    duration_s: int | None
    cost_usd: float | None

    @classmethod
    def from_payload(cls, p: EpisodePayload) -> "Episode":
        return cls(
            task_id=p.task_id,
            user_request=p.user_request,
            plan_summary=p.plan_summary,
            outcome=p.outcome,
            user_rating=p.user_rating,
            duration_s=p.duration_s,
            cost_usd=p.cost_usd,
        )

    def to_prompt_block(self) -> str:
        rating = f"{self.user_rating:.2f}" if self.user_rating is not None else "N/A"
        return (
            f"- request: {self.user_request[:200]}\n"
            f"  outcome: {self.outcome} (rating={rating})\n"
            f"  plan_summary: {self.plan_summary[:400]}"
        )


async def retrieve_similar_episodes(
    *,
    user_request: str,
    user_id: str,
    top_k: int = DEFAULT_TOP_K,
) -> list[Episode]:
    """召回相似历史任务。

    流程:
        1. flag 关 → 返回 [](默认行为)
        2. flag 开 → 调 qdrant_client.search_episodes(只取 outcome=success 的)
        3. 任何失败 → 返回 [](已在 qdrant_client 内 graceful)
    """
    if not EPISODE_RETRIEVAL_ENABLED:
        return []

    uid = str(user_id or "").strip()
    if not uid:
        log.warning("planner.episode_retrieval.skipped_empty_user_id")
        return []

    payloads = await _qdrant_search_episodes(
        query_text=user_request,
        user_id=uid,
        top_k=top_k,
        only_success=EPISODE_ONLY_SUCCESS,
    )

    episodes = [Episode.from_payload(p) for p in payloads]
    log.info(
        "planner.episode_retrieval.hit",
        user_id=user_id,
        top_k=top_k,
        n_returned=len(episodes),
    )
    return episodes


def format_episodes_for_prompt(episodes: list[Episode]) -> str:
    if not episodes:
        return ""
    return "\n".join(ep.to_prompt_block() for ep in episodes)


def summarize_available_skills(skills_index: list[dict[str, Any]]) -> str:
    """把已有 Skill 列表压缩为 Planner 可读的 name+description 摘要。

    `skills_index` 形如 `[{"skill_id": "...", "name": "...", "description": "..."}, ...]`,
    上游(planner_agent.py)从 SkillRegistry 取。
    """
    if not skills_index:
        return ""
    lines = []
    for s in skills_index[:30]:  # 上限保护,过多会污染 Planner context
        sid = s.get("skill_id") or s.get("name") or "?"
        name = s.get("name") or sid
        desc = (s.get("description") or "").strip().replace("\n", " ")[:200]
        lines.append(f"- {sid} ({name}): {desc}")
    return "\n".join(lines)


def summarize_available_mcp_tools(mcp_tools: list[dict[str, str]]) -> str:
    """把 MCP 工具白名单压缩为 Planner 可读的清单。

    `mcp_tools` 形如 `[{"uri": "mcp://search/web_search", "desc": "..."}, ...]`。
    """
    if not mcp_tools:
        # 兜底:即使调用方未提供,也给一份默认清单(与 prompts.py 内嵌的对齐)
        return (
            "- mcp://search/web_search:网页搜索\n"
            "- mcp://search/web_fetch:抓取 URL 正文\n"
            "- mcp://image_tools/download_batch:批量下载图片\n"
            "- mcp://image_tools/quality_check:图片质检\n"
            "- mcp://audio_tools/tts:语音合成\n"
            "- mcp://video_tools/compose:视频合成\n"
            "- mcp://document_tools/pdf_extract:PDF 文本抽取\n"
            "- mcp://oss/upload:对象存储上传"
        )
    return "\n".join(f"- {t['uri']}:{t.get('desc', '')}" for t in mcp_tools[:60])
