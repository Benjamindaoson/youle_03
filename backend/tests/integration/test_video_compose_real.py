"""真实 MoviePy 合成测试(需要 ffmpeg 二进制)。

跑法:确保系统装了 ffmpeg(`which ffmpeg`)+ pip 装了 moviepy/pillow。
本测试不需要 OSS / Redis / Celery — 直接调 mcp-video-tools._do_compose 同步实现。

跳过条件:
- ffmpeg 不在 PATH
- moviepy 没装
"""
from __future__ import annotations
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# 让 mcp_servers 可 import
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _moviepy_available() -> bool:
    try:
        import moviepy.editor  # noqa: F401

        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not (_ffmpeg_available() and _moviepy_available()),
    reason="ffmpeg 或 moviepy 不可用,真实合成测试跳过",
)


@pytest.fixture
def tmp_workdir(tmp_path) -> Path:
    return tmp_path


@pytest.fixture
def synthetic_inputs(tmp_workdir: Path):
    """合成 2 张纯色图 + 1 段静音 mp3 + 1 段静音 mp3(BGM)。"""
    from PIL import Image

    img1 = tmp_workdir / "img1.jpg"
    img2 = tmp_workdir / "img2.jpg"
    Image.new("RGB", (1080, 1920), (255, 100, 100)).save(img1, "JPEG")
    Image.new("RGB", (1080, 1920), (100, 255, 100)).save(img2, "JPEG")

    voice = tmp_workdir / "voice.mp3"
    bgm = tmp_workdir / "bgm.mp3"
    for path, dur in [(voice, 4), (bgm, 4)]:
        subprocess.run(
            [
                "ffmpeg",
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=r=44100:cl=mono:d={dur}",
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "64k",
                "-y",
                str(path),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
    return {
        "voice_ref": str(voice),
        "bgm_ref": str(bgm),
        "image_refs": [str(img1), str(img2)],
    }


def test_do_compose_produces_real_mp4(tmp_workdir: Path, synthetic_inputs, monkeypatch):
    """直接调 _do_compose,不走 OSS;改用本地路径 + monkeypatch _put_oss 写本地。"""
    from mcp_servers.video_tools import server as vts

    out_mp4 = tmp_workdir / "out.mp4"

    def fake_put_oss(key: str, data: bytes, content_type: str) -> str:
        out_mp4.write_bytes(data)
        return f"oss://test/{key}"

    monkeypatch.setattr(vts, "_put_oss", fake_put_oss)

    oss_ref, duration, size_bytes = vts._do_compose(
        voice_ref=synthetic_inputs["voice_ref"],
        bgm_ref=synthetic_inputs["bgm_ref"],
        image_refs=synthetic_inputs["image_refs"],
        duration=4,
        subtitle="测试字幕。",
        resolution=(640, 360),  # 用小分辨率加速
        bgm_volume=0.2,
        voice_volume=1.0,
    )

    assert oss_ref.startswith("oss://test/videos/")
    assert duration == 4
    assert size_bytes > 0
    assert out_mp4.exists()
    assert out_mp4.stat().st_size > 0

    # 用 ffprobe 确认是有效 mp4
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type",
            "-of",
            "json",
            str(out_mp4),
        ],
        capture_output=True,
        timeout=30,
    )
    assert probe.returncode == 0, probe.stderr.decode()
    import json

    info = json.loads(probe.stdout)
    codec_types = {s.get("codec_type") for s in info.get("streams", [])}
    assert "video" in codec_types, f"mp4 缺 video 流: {info}"
    # 时长接近预期(±0.5s)
    actual_duration = float(info["format"]["duration"])
    assert 3.5 <= actual_duration <= 4.5, f"实际时长 {actual_duration}s"


def test_subtitle_align_chunks_text():
    import asyncio

    from mcp_servers.video_tools.server import subtitle_align

    out = asyncio.run(
        subtitle_align(
            {"text": "第一句。第二句。第三句。第四句。", "duration": 60}
        )
    )
    chunks = out["chunks"]
    assert len(chunks) == 4
    assert chunks[0]["start"] == 0.0
    assert chunks[-1]["end"] == 60.0
    assert chunks[0]["text"] == "第一句"
