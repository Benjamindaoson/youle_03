"""Agent 3 扩展 handlers — V1.5 范围。

走 mcp-image-tools 的 bg_remove / enhance;
image_generate / image_edit / image_describe 走 LiteLLM 多模态(铁律 7/13)。
"""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

import structlog

from agents._common import llm
from agents._common.flywheel_emitter import emit
from agents._common.mcp_client import mcp_client
from agents._common.memory_client import build_pref_context, get_user_prefs
from agents._common.prompts import IMAGE_DESCRIBE_SYSTEM, IMAGE_EDIT_SYSTEM, IMAGE_GENERATE_SYSTEM
from agents._common.protocol import AgentResult, AgentTask, ArtifactRef

log = structlog.get_logger(__name__)


def _make_mcp_handler(tool_name: str, *, artifact_type: str = "image"):
    async def _handler(task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        args: dict[str, Any] = {**(task.parameters or {}), **(task.inputs or {})}
        args.pop("_prompt", None)
        out = await mcp_client.call_tool(
            server="image_tools", tool=tool_name, arguments=args
        )
        if out.get("_failed"):
            return AgentResult(
                task_id=task.task_id,
                step_id=task.step_id,
                status="failed",
                error_detail={"tool": tool_name, "error": out.get("error", "unknown")},
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        ref = out.get("oss_ref") or f"oss://artifacts/{task.task_id}/{task.step_id}.png"
        meta = {k: v for k, v in out.items() if k != "oss_ref"}
        return AgentResult(
            task_id=task.task_id,
            step_id=task.step_id,
            status="completed",
            output=ArtifactRef(
                artifact_id=uuid4(),
                type=artifact_type,
                reference=ref,
                extra_metadata=meta,
            ),
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    _handler.__name__ = f"{tool_name}_handler"
    return _handler


bg_remove_handler = _make_mcp_handler("bg_remove")
enhance_handler = _make_mcp_handler("enhance")


async def image_generate_handler(task: AgentTask) -> AgentResult:
    """文生图(走 LiteLLM 路由的图像生成模型)。

    产物 normalize:LLM 不同图模型返回格式不一:
      - oss://...                  → 直接用
      - http(s)://... + .png/.jpg  → 下载到 OSS
      - data:image/...;base64,...  → decode 后写 OSS
      - 其他/失败                 → fallback 占位 ref
    """
    t0 = time.monotonic()
    prompt = task.inputs.get("_prompt") or task.inputs.get("prompt", "")

    # Inject user style preferences from flywheel memory
    user_prefs = await get_user_prefs(str(task.user_id))
    pref_ctx = build_pref_context(user_prefs)
    if pref_ctx:
        prompt = f"{prompt}\n\n{pref_ctx}"

    from agents.image_agent.xhs_image_router import TASK_TYPE_TO_KIND, generate_with_xhs_model_chain, resolve_visual_kind

    params = task.parameters or {}
    use_xhs = task.task_type in TASK_TYPE_TO_KIND or bool(params.get("xhs_visual_kind"))
    trail: list[dict[str, Any]] = []
    if use_xhs:
        kind = resolve_visual_kind(task.task_type, task.parameters)
        tt = task.task_type if task.task_type in TASK_TYPE_TO_KIND else "image_generate"
        try:
            resp, trail = await generate_with_xhs_model_chain(
                logical_task_type=tt,
                messages=[
                    {"role": "system", "content": IMAGE_GENERATE_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                visual_kind=kind,
                base_routing_hints=task.routing_hints,
            )
        except Exception as e:
            log.exception("xhs_image_generate.chain_failed", err=str(e))
            return AgentResult(
                task_id=task.task_id,
                step_id=task.step_id,
                status="failed",
                error_detail={"reason": "xhs_chain_failed", "msg": str(e)},
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
    else:
        trail = []
        resp = await llm.complete(
            task_type="image_generate",
            messages=[
                {"role": "system", "content": IMAGE_GENERATE_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            routing_hints=task.routing_hints,
        )

    ref, normalized_via = await _normalize_image_artifact(
        resp_content=resp.content if isinstance(resp.content, str) else "",
        task_id=str(task.task_id),
        step_id=task.step_id,
    )

    await emit(
        signal_type="trace",
        payload={
            "task_id": str(task.task_id),
            "step_id": task.step_id,
            "agent_id": "agent_3",
            "task_type": task.task_type,
            "model": resp.model,
            "normalized_via": normalized_via,
            "xhs_router_trail": trail,
        },
    )

    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="completed",
        output=ArtifactRef(
            artifact_id=uuid4(),
            type="image",
            reference=ref,
            extra_metadata={
                "model": resp.model,
                "prompt": prompt[:200],
                "normalized_via": normalized_via,
                "xhs_router_trail": trail,
            },
        ),
        cost_usd=resp.cost_usd,
        duration_ms=int((time.monotonic() - t0) * 1000),
        model_used=resp.model,
    )


async def _normalize_image_artifact(
    resp_content: str,
    *,
    task_id: str,
    step_id: str,
) -> tuple[str, str]:
    """把 LLM 多模态响应规范化成 OSS reference。返回 (ref, normalized_via)。"""
    import base64
    import re
    from contextlib import suppress

    from agents._common.oss_writer import put_bytes

    fallback_ref = f"oss://artifacts/{task_id}/{step_id}.png"
    text = (resp_content or "").strip()

    # 1. 已是 oss:// 引用
    if text.startswith("oss://"):
        return text, "oss_ref"

    # 2. data URI (base64)
    m = re.match(r"^data:image/(\w+);base64,(.+)$", text, flags=re.DOTALL)
    if m:
        ext = m.group(1)
        with suppress(Exception):
            payload = base64.b64decode(m.group(2))
            ref = await put_bytes(
                key=f"artifacts/{task_id}/{step_id}.{ext}",
                data=payload,
                content_type=f"image/{ext}",
            )
            return ref, "data_uri"
        return fallback_ref, "data_uri_decode_failed"

    # 3. http(s) URL → 下载到 OSS(避免上游 URL 失效)
    if text.startswith(("http://", "https://")) and len(text.split()) == 1:
        with suppress(Exception):
            import httpx as _httpx

            async with _httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
                r = await c.get(text)
                r.raise_for_status()
                ext = (text.rsplit(".", 1)[-1] or "png")[:4].lower()
                if ext not in ("png", "jpg", "jpeg", "webp"):
                    ext = "png"
                ref = await put_bytes(
                    key=f"artifacts/{task_id}/{step_id}.{ext}",
                    data=r.content,
                    content_type=f"image/{ext}",
                )
                return ref, "downloaded_url"
        return fallback_ref, "url_download_failed"

    # 4. fallback
    return fallback_ref, "fallback"


async def image_edit_handler(task: AgentTask) -> AgentResult:
    """图生图(局部重绘 / 扩图)— V1 走多模态 LLM + edit-aware 提示词。

    输入:
      image_ref: 参考图 OSS 引用或 URL
      _prompt: 编辑指令(必填)
    V1.5 接 SDXL Inpaint 时替换此 handler。
    """
    t0 = time.monotonic()
    image_ref = (
        task.inputs.get("image_ref")
        or task.inputs.get("ref")
        or task.parameters.get("image_ref")
    )
    edit_instruction = task.inputs.get("_prompt") or task.inputs.get("prompt", "")

    user_content: Any
    if image_ref:
        user_content = [
            {"type": "text", "text": f"编辑指令: {edit_instruction}"},
            {"type": "image_url", "image_url": {"url": str(image_ref)}},
        ]
    else:
        user_content = f"编辑指令(无参考图): {edit_instruction}"

    from agents.image_agent.xhs_image_router import generate_with_xhs_model_chain

    params = task.parameters or {}
    use_xhs = (
        task.task_type == "xhs_local_edit_image"
        or params.get("xhs_visual_kind") == "local_edit"
    )
    messages = [
        {"role": "system", "content": IMAGE_EDIT_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    trail: list[dict[str, Any]] = []
    if use_xhs:
        try:
            resp, trail = await generate_with_xhs_model_chain(
                logical_task_type="xhs_local_edit_image",
                messages=messages,
                visual_kind="local_edit",
                base_routing_hints=task.routing_hints,
            )
        except Exception as e:
            log.exception("xhs_image_edit.chain_failed", err=str(e))
            return AgentResult(
                task_id=task.task_id,
                step_id=task.step_id,
                status="failed",
                error_detail={"reason": "xhs_chain_failed", "msg": str(e)},
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
    else:
        resp = await llm.complete(
            task_type="image_generate",
            messages=messages,
            routing_hints=task.routing_hints,
        )

    ref, normalized_via = await _normalize_image_artifact(
        resp_content=resp.content if isinstance(resp.content, str) else "",
        task_id=str(task.task_id),
        step_id=task.step_id,
    )

    await emit(
        signal_type="trace",
        payload={
            "task_id": str(task.task_id),
            "step_id": task.step_id,
            "agent_id": "agent_3",
            "task_type": task.task_type,
            "model": resp.model,
            "has_ref_image": bool(image_ref),
            "normalized_via": normalized_via,
            "xhs_router_trail": trail,
        },
    )

    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="completed",
        output=ArtifactRef(
            artifact_id=uuid4(),
            type="image",
            reference=ref,
            extra_metadata={
                "model": resp.model,
                "image_ref": image_ref,
                "edit_instruction": edit_instruction[:200],
                "normalized_via": normalized_via,
                "xhs_router_trail": trail,
            },
        ),
        cost_usd=resp.cost_usd,
        duration_ms=int((time.monotonic() - t0) * 1000),
        model_used=resp.model,
    )


async def image_describe_handler(task: AgentTask) -> AgentResult:
    """图理解 — 走 LiteLLM 多模态。返回文本到 OSS。"""
    t0 = time.monotonic()
    image_ref = (
        task.inputs.get("image_ref")
        or task.inputs.get("ref")
        or task.parameters.get("image_ref")
    )
    user_msg = task.inputs.get("_prompt") or "请描述这张图的核心元素。"
    resp = await llm.complete(
        task_type="image_describe",
        messages=[
            {"role": "system", "content": IMAGE_DESCRIBE_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": str(user_msg)},
                    {"type": "image_url", "image_url": {"url": str(image_ref)}},
                ]
                if image_ref
                else str(user_msg),
            },
        ],
        routing_hints=task.routing_hints,
    )
    from agents._common.oss_writer import put_text

    oss_ref = await put_text(
        key=f"artifacts/{task.task_id}/{task.step_id}.txt", content=resp.content
    )

    await emit(
        signal_type="trace",
        payload={
            "task_id": str(task.task_id),
            "step_id": task.step_id,
            "agent_id": "agent_3",
            "task_type": "image_describe",
            "model": resp.model,
            "has_image": bool(image_ref),
        },
    )

    return AgentResult(
        task_id=task.task_id,
        step_id=task.step_id,
        status="completed",
        output=ArtifactRef(
            artifact_id=uuid4(),
            type="text",
            reference=oss_ref,
            extra_metadata={"model": resp.model, "image_ref": image_ref},
        ),
        cost_usd=resp.cost_usd,
        duration_ms=int((time.monotonic() - t0) * 1000),
        model_used=resp.model,
    )
