from __future__ import annotations


def test_image_generation_model_env_is_used_by_backend_router() -> None:
    from app.config import settings
    from app.router import TASK_TYPE_ROUTING

    assert settings.IMAGE_GENERATION_MODEL == "openai/gpt-5.4-image-2"
    assert TASK_TYPE_ROUTING["image_generate"]["primary"] == [settings.IMAGE_GENERATION_MODEL]
    assert TASK_TYPE_ROUTING["batch_generate"]["primary"] == [settings.IMAGE_GENERATION_MODEL]
