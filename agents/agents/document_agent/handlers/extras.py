"""Agent 2 扩展 handlers — 走 mcp-document-tools(铁律 13),MCP 失败时 LLM 降级。

LLM 降级策略:
- pdf_extract / pdf_ocr:LLM 生成"提取失败"占位文本,保持 completed 状态
- pptx/xlsx/docx_assemble:LLM 生成结构化文本大纲,标注 degraded=True
"""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

import structlog

from agents._common import llm
from agents._common.flywheel_emitter import emit
from agents._common.mcp_client import mcp_client
from agents._common.oss_writer import put_text
from agents._common.protocol import AgentResult, AgentTask, ArtifactRef

log = structlog.get_logger(__name__)

ARTIFACT_TYPE_BY_TOOL = {
    "pptx_assemble": "document",
    "xlsx_assemble": "document",
    "docx_assemble": "document",
    "pdf_extract": "text",
    "pdf_ocr": "text",
}

_ASSEMBLE_FALLBACK_PROMPT = """\
MCP 文档工具暂时不可用。请根据以下参数,生成一份结构化的文档内容大纲(Markdown 格式),
供用户了解文档应包含的内容。注明这是降级输出,实际文档文件需后续重试生成。

参数: {args}
"""

_EXTRACT_FALLBACK_PROMPT = """\
PDF 提取工具暂时不可用。请根据以下文件信息生成一条简洁说明,
告知用户提取失败的情况并建议重试。

文件参数: {args}
"""


def _make_handler(tool_name: str):
    async def _handler(task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        args: dict[str, Any] = {**(task.parameters or {}), **(task.inputs or {})}
        args.pop("_prompt", None)
        artifact_type = ARTIFACT_TYPE_BY_TOOL.get(tool_name, "document")
        degraded = False

        out = await mcp_client.call_tool(
            server="document_tools",
            tool=tool_name,
            arguments=args,
        )

        if out.get("_failed"):
            log.warning(
                "document.mcp_failed_llm_fallback",
                tool=tool_name,
                err=out.get("error"),
            )
            # LLM 降级:生成文本占位内容,不直接 fail
            is_extract = tool_name in ("pdf_extract", "pdf_ocr")
            template = _EXTRACT_FALLBACK_PROMPT if is_extract else _ASSEMBLE_FALLBACK_PROMPT
            try:
                resp = await llm.complete(
                    task_type="long_writing",
                    messages=[
                        {
                            "role": "user",
                            "content": template.format(args=str(args)[:400]),
                        }
                    ],
                    routing_hints=task.routing_hints,
                    max_tokens=600,
                )
                fallback_text = resp.content
            except Exception as e:
                log.warning("document.llm_fallback_failed", err=str(e))
                fallback_text = f"[文档工具({tool_name})暂时不可用,请稍后重试。原始错误: {out.get('error', 'unknown')}]"

            ref = await put_text(
                key=f"artifacts/{task.task_id}/{task.step_id}.txt",
                content=fallback_text,
            )
            degraded = True
            out = {"oss_ref": ref, "degraded": True, "fallback_reason": "mcp_tool_failed"}
            artifact_type = "text"

        ref = out.get("oss_ref")

        if not ref and tool_name in ("pdf_extract", "pdf_ocr"):
            ref = await put_text(
                key=f"artifacts/{task.task_id}/{task.step_id}.txt",
                content=out.get("text", ""),
            )

        meta = {k: v for k, v in out.items() if k not in ("oss_ref", "text")}
        meta["degraded"] = degraded

        await emit(
            signal_type="trace",
            payload={
                "task_id": str(task.task_id),
                "step_id": task.step_id,
                "agent_id": "agent_2",
                "task_type": tool_name,
                "degraded": degraded,
            },
        )

        return AgentResult(
            task_id=task.task_id,
            step_id=task.step_id,
            status="completed",
            output=ArtifactRef(
                artifact_id=uuid4(),
                type=artifact_type,
                reference=ref or f"oss://artifacts/{task.task_id}/{task.step_id}",
                extra_metadata=meta,
            ),
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    _handler.__name__ = f"{tool_name}_handler"
    return _handler


pptx_assemble_handler = _make_handler("pptx_assemble")
xlsx_assemble_handler = _make_handler("xlsx_assemble")
docx_assemble_handler = _make_handler("docx_assemble")
pdf_extract_handler = _make_handler("pdf_extract")
pdf_ocr_handler = _make_handler("pdf_ocr")
