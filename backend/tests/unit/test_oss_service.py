from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from botocore.exceptions import ClientError

from app.services import oss
from app.services.oss import OSSService


class FakeS3Client:
    def __init__(self, error_code: str, status_code: int | None = None) -> None:
        self.error_code = error_code
        self.status_code = status_code

    def head_object(self, **_: object) -> dict[str, object]:
        error_response: dict[str, object] = {
            "Error": {"Code": self.error_code, "Message": "missing"},
        }
        if self.status_code is not None:
            error_response["ResponseMetadata"] = {"HTTPStatusCode": self.status_code}
        raise ClientError(
            error_response=error_response,
            operation_name="HeadObject",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code", "status_code"),
    [
        ("AccessDenied", None),
        ("403", None),
        ("Forbidden", 403),
        ("", 403),
    ],
)
async def test_get_object_metadata_treats_access_denied_as_missing(
    monkeypatch: pytest.MonkeyPatch,
    error_code: str,
    status_code: int | None,
) -> None:
    async def run_inline(
        func: Callable[..., dict[str, object] | None], /, *args: Any, **kwargs: Any
    ) -> dict[str, object] | None:
        return func(*args, **kwargs)

    monkeypatch.setattr(oss.asyncio, "to_thread", run_inline)
    service = OSSService()
    service._s3 = FakeS3Client(error_code, status_code)

    assert await service.get_object_metadata("avatar/missing") is None
