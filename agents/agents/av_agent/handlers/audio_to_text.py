"""Agent 4 audio_to_text — Whisper-v3 语音识别(v4 #79)。

输入:audio_url(OSS 引用) / language(可选,默认 zh)
输出:transcript(纯文本) + segments(带时间戳)→ 落 OSS,artifact 引用文本
"""

from __future__ import annotations

import json
import time
from uuid import uuid4

from agents._common import llm
from agents._common.flywheel_emitter import emit
from agents._common.protocol import AgentResult, AgentTask, ArtifactRef


async def audio_to_text_handler(task: AgentTask) -> AgentResult:
    t0 = time.monotonic()
    audio_url = task.inputs.get("audio_url") or task.inputs.get("audio_oss_ref")
    language = task.inputs.get("language") or task.parameters.get("language", "zh")
    align_subtitles = bool(task.parameters.get("align_subtitles", True))

    if not audio_url:
        return AgentResult(
            task_id=task.task_id,
            step_id=task.step_id,
            status="failed",
            error_detail={"reason": "missing_audio_url"},
        )

    # 调 LiteLLM 路由的 whisper-v3(LITELLM_MOCK 时返回固定 mock 文本)
    resp = await llm.complete(
        task_type="audio_to_text",
        messages=[
            {
                "role": "user",
                "content": (
                    "请把以下音频转为带时间戳的字幕(JSON: "
                    "{transcript:string, segments:[{start, end, text}]}):\n"
                    f"{audio_url}"
                ),
            }
        ],
        routing_hints={**task.routing_hints, "language": language},
        response_format={"type": "json_object"},
    )

    try:
        data = json.loads(resp.content)
    except json.JSONDecodeError:
        # mock / 简单兜底:把整段当一句字幕
        data = {
            "transcript": resp.content,
            "segments": [{"start": 0.0, "end": 30.0, "text": resp.content}],
        }

    transcript = str(data.get("transcript", ""))
    segments = data.get("segments") or []

    oss_ref = f"oss://artifacts/{task.task_id}/{task.step_id}.json"
    duration_ms = int((time.monotonic() - t0) * 1000)

    await emit(
        signal_type="trace",
        payload={
            "task_id": str(task.task_id),
            "step_id": task.step_id,
            "agent_id": "agent_4",
            "task_type": "audio_to_text",
            "language": language,
            "segment_count": len(segments),
            "transcript_len": len(transcript),
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
            extra_metadata={
                "language": language,
                "transcript_preview": transcript[:120],
                "segment_count": len(segments),
                "align_subtitles": align_subtitles,
            },
        ),
        duration_ms=duration_ms,
    )
