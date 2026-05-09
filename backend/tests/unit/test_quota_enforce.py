"""配额执行单测(纯函数 + 推断逻辑)。"""

from __future__ import annotations

from app.services.quota_enforce import infer_task_kind


def test_infer_video_kind() -> None:
    assert infer_task_kind({"domain": "video"}) == "video"
    assert infer_task_kind({"domain": "av"}) == "video"


def test_infer_image_kind() -> None:
    assert infer_task_kind({"domain": "image"}) == "image"


def test_infer_document_kind() -> None:
    assert infer_task_kind({"domain": "document"}) == "document"


def test_infer_default_text() -> None:
    assert infer_task_kind({}) == "text"
    assert infer_task_kind({"domain": "unknown"}) == "text"


def test_infer_mixed() -> None:
    assert infer_task_kind({"domain": "mixed"}) == "mixed"
