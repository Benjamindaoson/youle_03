from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config.settings import Settings


def _production_settings(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "ENV": "prod",
        "JWT_SECRET": "a-production-secret-that-is-long-enough",
        "SMS_DEV_MODE": False,
        "ALIYUN_ACCESS_KEY": "access-key",
        "ALIYUN_SECRET_KEY": "secret-key",
        "ALIYUN_SMS_SIGN_NAME": "haole",
        "ALIYUN_SMS_TEMPLATE_CODE": "SMS_123",
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_non_dev_environment_rejects_universal_sms_code(env: str) -> None:
    with pytest.raises(ValidationError, match="SMS_DEV_MODE"):
        Settings(
            _env_file=None,
            **_production_settings(ENV=env, SMS_DEV_MODE=True),
        )


def test_production_sms_requires_provider_credentials() -> None:
    with pytest.raises(ValidationError, match="ALIYUN"):
        Settings(
            _env_file=None,
            **_production_settings(ALIYUN_SMS_TEMPLATE_CODE=""),
        )
