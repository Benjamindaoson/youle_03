"""Celery video_workflow 编排逻辑单测(不需要 ffmpeg / docker)。

策略:mock httpx + boto3 + redis,只验证 video_workflow 的步骤顺序和回写。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

# 让 backend tests 能 import 仓库根的 agents/*
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _build_task_payload() -> str:
    return json.dumps(
        {
            "task_id": str(uuid4()),
            "step_id": "video_compose",
            "agent_id": "agent_4",
            "task_type": "video_compose",
            "user_id": str(uuid4()),
            "conversation_id": str(uuid4()),
            "inputs": {
                "script": {"reference": "oss://test/script.txt"},
                "images": {"metadata": {"image_refs": ["oss://test/i1.jpg", "oss://test/i2.jpg"]}},
                "bgm": {"reference": "oss://test/bgm.mp3"},
            },
            "parameters": {"voice": "female_warm", "duration_field": "60s"},
            "routing_hints": {},
            "skill_id": "short_video",
            "skill_version": "0.5",
            "timeout_seconds": 600,
        }
    )


def test_video_workflow_happy_path() -> None:
    from agents.av_agent.celery_tasks import video_workflow as vw

    # mock OSS 读取(返回脚本文本)
    fake_script = "这是测试脚本。第二句话。第三句话。"

    def fake_read_oss(ref: str) -> bytes:
        if "script" in ref:
            return fake_script.encode("utf-8")
        return b""

    # mock httpx 客户端
    class FakeResp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeHttpClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url: str, json=None, **kw):
            if "tts" in url:
                return FakeResp({"oss_ref": "oss://test/tts.mp3", "duration_seconds": 12})
            if "compose" in url:
                return FakeResp(
                    {
                        "oss_ref": "oss://test/output.mp4",
                        "duration_seconds": 60,
                        "size_bytes": 1234567,
                    }
                )
            return FakeResp({})

    # mock redis xadd
    written: list[tuple[str, dict]] = []

    class FakeRedis:
        def xadd(self, stream: str, fields: dict):
            written.append((stream, fields))

        def close(self):
            pass

    with (
        patch.object(vw, "_read_oss", side_effect=fake_read_oss),
        patch("agents.av_agent.celery_tasks.video_workflow.httpx.Client", FakeHttpClient),
        patch("agents.av_agent.celery_tasks.video_workflow.redis.from_url", return_value=FakeRedis()),
    ):
        # 直接调内部函数(绕开 Celery 装饰器,用 .run 或直接调)
        result = vw.video_compose_workflow.run(_build_task_payload())

    assert result["status"] == "completed"
    assert result["oss_ref"] == "oss://test/output.mp4"

    # 验证 AgentResult 写回 agent_results:{task_id}
    assert len(written) == 1
    stream, fields = written[0]
    assert stream.startswith("agent_results:")
    payload = json.loads(fields["data"])
    assert payload["status"] == "completed"
    assert payload["step_id"] == "video_compose"
    assert payload["output"]["type"] == "video"
    assert payload["output"]["reference"] == "oss://test/output.mp4"
    assert payload["output"]["extra_metadata"]["image_count"] == 2
    assert payload["output"]["extra_metadata"]["voice_ref"] == "oss://test/tts.mp3"


def test_video_workflow_compose_failure_writes_failed_result() -> None:
    from agents.av_agent.celery_tasks import video_workflow as vw

    class FakeResp:
        def __init__(self, payload, status=200):
            self._payload = payload
            self._status = status

        def raise_for_status(self):
            if self._status >= 400:
                raise RuntimeError(f"http {self._status}")

        def json(self):
            return self._payload

    class FakeHttpClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, **kw):
            if "tts" in url:
                return FakeResp({"oss_ref": "oss://test/tts.mp3"})
            if "compose" in url:
                return FakeResp({"_failed": True, "error": "ffmpeg_not_found"}, status=200)
            return FakeResp({})

    written: list[tuple[str, dict]] = []

    class FakeRedis:
        def xadd(self, stream, fields):
            written.append((stream, fields))

        def close(self):
            pass

    with (
        patch.object(vw, "_read_oss", return_value=b"text"),
        patch("agents.av_agent.celery_tasks.video_workflow.httpx.Client", FakeHttpClient),
        patch("agents.av_agent.celery_tasks.video_workflow.redis.from_url", return_value=FakeRedis()),
    ):
        result = vw.video_compose_workflow.run(_build_task_payload())

    assert result["status"] == "failed"
    # 失败也写回流(让 TaskRunner 能感知失败)
    assert len(written) == 1
    payload = json.loads(written[0][1]["data"])
    assert payload["status"] == "failed"
    assert "compose_returned_error" in payload["error_detail"]["reason"]


def test_resolve_image_refs_handles_collection_metadata() -> None:
    from agents.av_agent.celery_tasks.video_workflow import _resolve_image_refs

    # 来自 image_process 的 ArtifactRef + image_collection metadata
    out = _resolve_image_refs(
        {"reference": "oss://test/manifest/", "metadata": {"image_refs": ["a", "b", "c"]}}
    )
    assert out == ["a", "b", "c"]

    # 直接 list
    assert _resolve_image_refs(["x", "y"]) == ["x", "y"]
    # 单 string
    assert _resolve_image_refs("z") == ["z"]
    # 空
    assert _resolve_image_refs({}) == []


def test_short_video_skill_loads() -> None:
    from app.services.skill_loader import load_skill_by_id

    skill = load_skill_by_id("short_video")
    assert skill["skill_id"] == "short_video"
    assert skill["scenario"] == "short_video"
    assert skill["visibility"] == "public"

    # 通用视频保持 5 步结构
    workflow = skill["workflow"]
    step_ids = [s["step_id"] for s in workflow]
    assert step_ids == ["research", "script", "image_process", "bgm", "video_compose"]

    # ADR-001-rev:Agent 编号
    by_id = {s["step_id"]: s for s in workflow}
    assert by_id["research"]["agent"] == "agent_1"
    assert by_id["script"]["agent"] == "agent_1"
    assert by_id["image_process"]["agent"] == "agent_3"
    assert by_id["bgm"]["agent"] == "agent_4"
    assert by_id["video_compose"]["agent"] == "agent_4"

    # V1 终审无 rollback action(铁律 14)
    final = by_id["video_compose"]["hitl_gate"]
    actions = [a["action"] for a in final["actions"]]
    assert "approve" in actions
    assert "rollback" not in actions
