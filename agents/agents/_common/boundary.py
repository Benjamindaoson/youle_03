"""Agent 边界检查(铁律 1/2:单一调度者 + Agent 编号锁定)。"""

from __future__ import annotations

from agents._common.protocol import AgentId, AgentTask

# 各 Agent 支持的 task_type 集合(与 docs/2_工程实现/4 个分任务 Agent 实现指南.md 对齐)
SUPPORTED_TASK_TYPES: dict[AgentId, set[str]] = {
    "agent_1": {
        "short_writing",
        "long_writing",
        "structured_writing",
        "summarization",
        "extraction",
        "analysis",
        "web_search",
        "web_scrape",
        "data_organize",
        "translation",
        "polish",
        "version_compare",
        "short_video_script",
        "short_video_hook",
        # 小红书图文
        "xhs_carousel_plan",
        "xhs_carousel_copy",
        "xhs_delivery_summary",
    },
    "agent_2": {
        "pptx_assemble",
        "pptx_modify",
        "pptx_extract",
        "xlsx_assemble",
        "xlsx_read",
        "xlsx_chart",
        "xlsx_format",
        "docx_assemble",
        "docx_modify",
        "docx_extract",
        "pdf_extract",
        "pdf_create",
        "pdf_watermark",
        "pdf_ocr",
        "image_concat_long",
    },
    "agent_3": {
        "image_generate",
        "image_edit",
        "image_compose",
        "batch_generate",
        "image_describe",
        "image_classify",
        "image_quality_check",
        "image_ocr",
        "image_inpaint",
        "image_outpaint",
        "image_enhance",
        "enhance",
        "background_remove",
        "bg_remove",
        "image_download",
        "style_extract",
        "style_transfer",
        # 小红书图模路由 task_type
        "xhs_cover_image",
        "xhs_slide_text_image",
        "xhs_product_image",
        "xhs_ambience_image",
        "xhs_series_image",
        "xhs_local_edit_image",
    },
    "agent_4": {
        "text_to_video",
        "image_to_video",
        "video_compose",
        "video_describe",
        "video_extract_frames",
        "audio_extract",
        "video_cut",
        "subtitle_generate",
        "subtitle_add",
        "bgm_add",
        "transition_apply",
        "tts_generate",
        "audio_to_text",
        "bgm_select",
    },
}


class BoundaryViolation(Exception):
    pass


def assert_task_in_boundary(agent_id: AgentId, task: AgentTask) -> None:
    if task.agent_id != agent_id:
        raise BoundaryViolation(f"task.agent_id={task.agent_id} != self={agent_id}")
    if task.task_type not in SUPPORTED_TASK_TYPES[agent_id]:
        raise BoundaryViolation(
            f"{agent_id} does not support task_type={task.task_type}; check Skill YAML"
        )
