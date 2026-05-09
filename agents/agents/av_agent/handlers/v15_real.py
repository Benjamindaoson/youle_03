"""Agent 4 V1.5 task_type 的真实现(铁律 11 override:PM 授权全量实现)。

每个 handler 走 MCP video_tools / audio_tools / LiteLLM 视频生成模型。
铁律 13 守住:工具走 MCP server,不直接调 ffmpeg / moviepy。
铁律 7 守住:LLM 走 LiteLLM。

10 个 task_type:
- text_to_video / image_to_video → LiteLLM(Veo / Seedance / Kling-2)
- video_describe → MCP video_tools.video_describe + LiteLLM 多模态
- video_extract_frames → MCP video_tools.extract_frames
- audio_extract → MCP video_tools.audio_extract
- video_cut → MCP video_tools.video_cut
- subtitle_generate → MCP audio_tools.subtitle_generate(Whisper)
- subtitle_add → MCP video_tools.subtitle_add(burn-in)
- bgm_add → MCP video_tools.bgm_add(混音)
- transition_apply → MCP video_tools.transition_apply
"""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

import structlog

from agents._common import llm
from agents._common.mcp_client import mcp_client
from agents._common.protocol import AgentResult, AgentTask, ArtifactRef

log = structlog.get_logger(__name__)


# ─── 公共构造 ───
def _ok_result(
    task: AgentTask,
    *,
    artifact_type: str,
    reference: str,
    metadata: dict[str, Any],
    started_at: float,
    cost_usd: float | None = None,
    model_used: str | None = None,
) -> AgentResult:
    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="completed",
        output=ArtifactRef(
            artifact_id=uuid4(),
            type=artifact_type,
            reference=reference,
            extra_metadata=metadata,
        ),
        cost_usd=cost_usd,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        model_used=model_used,
    )


def _fail_result(task: AgentTask, *, reason: str, **extra: Any) -> AgentResult:
    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="failed",
        error_detail={"reason": reason, **extra},
    )


# ─── 1. text_to_video — LiteLLM Veo / Seedance / Kling-2 ───
async def text_to_video_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()
    prompt = task.inputs.get("_prompt") or task.inputs.get("prompt", "")
    if not prompt:
        return _fail_result(task, reason="missing_prompt")
    duration = task.parameters.get("duration", 6)
    aspect = task.parameters.get("aspect", "16:9")
    try:
        resp = await llm.complete(
            task_type="text_to_video",
            messages=[{"role": "user", "content": prompt}],
            routing_hints=task.routing_hints,
        )
        # LiteLLM 视频模型一般返回 oss_ref / URL,走 normalize
        from agents.image_agent.handlers.extras import _normalize_image_artifact

        ref, via = await _normalize_image_artifact(
            resp_content=resp.content if isinstance(resp.content, str) else "",
            task_id=str(task.task_id),
            step_id=task.step_id,
        )
        # 视频用 .mp4 后缀(normalize 默认 .png — 修正)
        if ref.endswith(".png"):
            ref = ref.replace(".png", ".mp4")
        return _ok_result(
            task,
            artifact_type="video",
            reference=ref,
            metadata={
                "model": resp.model,
                "duration_target": duration,
                "aspect": aspect,
                "normalized_via": via,
                "prompt": prompt[:200],
            },
            started_at=t0,
            cost_usd=resp.cost_usd,
            model_used=resp.model,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("text_to_video.failed", err=str(e))
        return _fail_result(task, reason="llm_error", error=str(e)[:200])


# ─── 2. image_to_video — 同 text_to_video,prompt 含图引用 ───
async def image_to_video_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()
    image_ref = (
        task.inputs.get("image_ref")
        or task.inputs.get("ref")
        or task.parameters.get("image_ref")
    )
    if not image_ref:
        return _fail_result(task, reason="missing_image_ref")
    prompt = task.inputs.get("_prompt") or task.inputs.get("prompt", "make this image animate")
    try:
        resp = await llm.complete(
            task_type="image_to_video",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": str(image_ref)}},
                    ],
                }
            ],
            routing_hints=task.routing_hints,
        )
        from agents.image_agent.handlers.extras import _normalize_image_artifact

        ref, via = await _normalize_image_artifact(
            resp_content=resp.content if isinstance(resp.content, str) else "",
            task_id=str(task.task_id),
            step_id=task.step_id,
        )
        if ref.endswith(".png"):
            ref = ref.replace(".png", ".mp4")
        return _ok_result(
            task,
            artifact_type="video",
            reference=ref,
            metadata={
                "model": resp.model,
                "image_ref": str(image_ref),
                "normalized_via": via,
            },
            started_at=t0,
            cost_usd=resp.cost_usd,
            model_used=resp.model,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("image_to_video.failed", err=str(e))
        return _fail_result(task, reason="llm_error", error=str(e)[:200])


# ─── 3. video_describe — 抽帧 + LiteLLM 多模态 ───
async def video_describe_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()
    video_ref = (
        task.inputs.get("video_ref")
        or task.inputs.get("ref")
        or task.parameters.get("video_ref")
    )
    if not video_ref:
        return _fail_result(task, reason="missing_video_ref")
    n = int(task.parameters.get("n_frames", 5))
    try:
        # 1) 抽帧
        frames_out = await mcp_client.call_tool(
            server="video_tools",
            tool="video_describe",
            arguments={"ref": str(video_ref), "n_frames": n},
        )
        if frames_out.get("_failed"):
            return _fail_result(task, reason="extract_frames_failed", **frames_out)
        frame_refs = [f["oss_ref"] for f in frames_out.get("frames", [])]
        # 2) 多模态描述
        content_parts: list[dict[str, Any]] = [
            {"type": "text", "text": task.inputs.get("_prompt") or "请描述这段视频"}
        ]
        for fref in frame_refs[:n]:
            content_parts.append(
                {"type": "image_url", "image_url": {"url": fref}}
            )
        resp = await llm.complete(
            task_type="video_describe",
            messages=[{"role": "user", "content": content_parts}],
            routing_hints=task.routing_hints,
        )
        from agents._common.oss_writer import put_text

        oss_ref = await put_text(
            key=f"artifacts/{task.task_id}/{task.step_id}.txt", content=resp.content
        )
        return _ok_result(
            task,
            artifact_type="text",
            reference=oss_ref,
            metadata={
                "model": resp.model,
                "frames_used": len(frame_refs),
                "video_duration": frames_out.get("duration"),
            },
            started_at=t0,
            cost_usd=resp.cost_usd,
            model_used=resp.model,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("video_describe.failed", err=str(e))
        return _fail_result(task, reason="error", error=str(e)[:200])


# ─── 公共 MCP 调用工厂 ─── 给纯 MCP 包装的 handler 用
def _make_mcp_handler(
    *,
    server: str,
    tool: str,
    artifact_type: str,
    required_keys: list[str],
):
    async def _handler(task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        args: dict[str, Any] = {**(task.parameters or {}), **(task.inputs or {})}
        args.pop("_prompt", None)
        # 校验必填
        missing = [k for k in required_keys if k not in args and k != "ref"]
        # ref 兼容多名(ref / oss_ref / url / video_ref)
        if "ref" in required_keys and not any(
            args.get(k) for k in ("ref", "oss_ref", "url", "video_ref")
        ):
            missing.append("ref")
        if missing:
            return _fail_result(task, reason="missing_args", missing=missing)
        try:
            out = await mcp_client.call_tool(server=server, tool=tool, arguments=args)
            if out.get("_failed"):
                return _fail_result(
                    task, reason=f"{tool}_failed", error=out.get("error", "unknown")
                )
            ref = out.get("oss_ref")
            if not ref:
                return _fail_result(task, reason="no_artifact", **out)
            metadata = {k: v for k, v in out.items() if k != "oss_ref"}
            return _ok_result(
                task,
                artifact_type=artifact_type,
                reference=ref,
                metadata=metadata,
                started_at=t0,
            )
        except Exception as e:  # noqa: BLE001
            log.warning(f"{tool}.failed", err=str(e))
            return _fail_result(task, reason="error", error=str(e)[:200])

    _handler.__name__ = f"{tool}_handler"
    return _handler


# ─── 4-10:走 MCP video_tools / audio_tools ───
video_extract_frames_handler = _make_mcp_handler(
    server="video_tools",
    tool="extract_frames",
    artifact_type="image_collection",
    required_keys=["ref"],
)
audio_extract_handler = _make_mcp_handler(
    server="video_tools",
    tool="audio_extract",
    artifact_type="audio",
    required_keys=["ref"],
)
video_cut_handler = _make_mcp_handler(
    server="video_tools",
    tool="video_cut",
    artifact_type="video",
    required_keys=["ref"],
)
subtitle_generate_handler = _make_mcp_handler(
    server="audio_tools",
    tool="subtitle_generate",
    artifact_type="subtitle",
    required_keys=[],  # audio_url / ref 在 args 里灵活
)
subtitle_add_handler = _make_mcp_handler(
    server="video_tools",
    tool="subtitle_add",
    artifact_type="video",
    required_keys=["ref"],
)
bgm_add_handler = _make_mcp_handler(
    server="video_tools",
    tool="bgm_add",
    artifact_type="video",
    required_keys=[],
)
transition_apply_handler = _make_mcp_handler(
    server="video_tools",
    tool="transition_apply",
    artifact_type="video",
    required_keys=[],
)


# 顺一个字典给 main.py 注册 — V1.5 全部 10 个真 handler
V15_REAL_HANDLERS: dict[str, Any] = {
    "text_to_video": text_to_video_handler,
    "image_to_video": image_to_video_handler,
    "video_describe": video_describe_handler,
    "video_extract_frames": video_extract_frames_handler,
    "audio_extract": audio_extract_handler,
    "video_cut": video_cut_handler,
    "subtitle_generate": subtitle_generate_handler,
    "subtitle_add": subtitle_add_handler,
    "bgm_add": bgm_add_handler,
    "transition_apply": transition_apply_handler,
}
