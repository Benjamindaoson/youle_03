"""Skill step 静态输入渲染与模板水合 — 从 compiler 拆分以降低单文件复杂度。"""

from __future__ import annotations

import os
import re
from typing import Any

from jinja2 import Template

STEP_OUTPUT_RE = re.compile(r"^\s*\{\{\s*([A-Za-z0-9_\-]+)\.output\s*\}\}\s*$")


def render_static_input(
    value: Any,
    *,
    fields: dict[str, Any],
    step_context: dict[str, Any],
    tmpl_globals: dict[str, Any] | None = None,
) -> Any:
    g = tmpl_globals or {}
    if isinstance(value, str):
        matched = STEP_OUTPUT_RE.match(value)
        if matched:
            ctx = step_context.get(matched.group(1)) or {}
            return {
                "reference": ctx.get("artifact_ref") or ctx.get("reference"),
                "type": ctx.get("type"),
                "metadata": ctx.get("metadata") or {},
            }
        if "{{" in value and "}}" in value:
            return Template(value).render(**{**g, **fields, **step_context})
        return value
    if isinstance(value, list):
        return [
            render_static_input(item, fields=fields, step_context=step_context, tmpl_globals=g)
            for item in value
        ]
    if isinstance(value, dict):
        return {
            key: render_static_input(item, fields=fields, step_context=step_context, tmpl_globals=g)
            for key, item in value.items()
        }
    return value


async def hydrate_steps_for_templates(
    step_context: dict[str, dict[str, Any]],
    step_results: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """为已完成 step 拉取 OSS 文本/JSON摘要,写入 content_* 供模板使用。"""
    from agents.orchestrator_agent.langgraph_runner.artifact_body import fetch_artifact_text_excerpt

    budget = int(os.getenv("ORCH_HYDRATE_BUDGET_BYTES", str(768 * 1024)))
    used = 0
    out: dict[str, dict[str, Any]] = {}
    for sid, ctx in step_context.items():
        base = dict(ctx)
        ref = base.get("artifact_ref")
        if not ref:
            out[sid] = {**base, "content_text": "", "content_object": None, "content_hydrated": False}
            continue
        rem = budget - used
        if rem <= 0:
            out[sid] = {**base, "content_text": "", "content_object": None, "content_hydrated": False}
            continue
        excerpt = await fetch_artifact_text_excerpt(
            reference=str(ref),
            artifact_type=(step_results.get(sid) or {}).get("artifact_type"),
            max_bytes=min(256 * 1024, rem),
        )
        txt = excerpt.get("text") or ""
        used += len(txt.encode("utf-8", errors="ignore"))
        out[sid] = {
            **base,
            "content_text": txt,
            "content_object": excerpt.get("object"),
            "content_truncated": bool(excerpt.get("truncated")),
            "content_kind": excerpt.get("kind"),
            "content_hydrated": True,
        }
    return out
