from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.api import upload
from app.api.auth import _create_token
from app.db import get_session
from app.main import app
from app.models.user import User


class FakeSession:
    def __init__(self, user: User | None) -> None:
        self.user = user
        self.committed = False

    async def get(self, model: object, item_id: UUID) -> User | None:
        if model is not User or self.user is None or self.user.id != item_id:
            return None
        return self.user

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, obj: object) -> None:
        return None


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def auth_headers(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {_create_token(user_id)}"}


@pytest.mark.asyncio
async def test_avatar_sign_requires_auth(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_presign(**_: object) -> tuple[str, str, int]:
        return "avatar/unused/a.png", "https://upload.example/a.png", 600

    monkeypatch.setattr(upload.oss_service, "create_presigned_put", fake_presign)

    response = await client.post(
        "/api/upload/sign",
        json={"file_name": "avatar.png", "content_type": "image/png", "purpose": "avatar"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_avatar_sign_scopes_object_key_to_current_user(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = uuid4()
    seen: dict[str, object] = {}

    async def fake_presign(**kwargs: object) -> tuple[str, str, int]:
        seen.update(kwargs)
        return (
            f"avatar/{user_id}/20260506/avatar.png",
            "https://upload.example/avatar.png",
            600,
        )

    monkeypatch.setattr(upload.oss_service, "create_presigned_put", fake_presign)

    response = await client.post(
        "/api/upload/sign",
        headers=auth_headers(user_id),
        json={"file_name": "avatar.png", "content_type": "image/png", "purpose": "avatar"},
    )

    assert response.status_code == 200
    assert seen["purpose"] == f"avatar/{user_id}"
    assert response.json()["object_key"].startswith(f"avatar/{user_id}/")


@pytest.mark.asyncio
async def test_avatar_sign_rejects_non_image_content_type(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_presign(**_: object) -> tuple[str, str, int]:
        return "avatar/unused/a.txt", "https://upload.example/a.txt", 600

    monkeypatch.setattr(upload.oss_service, "create_presigned_put", fake_presign)

    response = await client.post(
        "/api/upload/sign",
        headers=auth_headers(uuid4()),
        json={"file_name": "avatar.txt", "content_type": "text/plain", "purpose": "avatar"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_avatar_confirm_updates_current_user_avatar_url(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = User(
        id=uuid4(),
        phone="13800138000",
        nickname="老板",
        plan="free",
        created_at=datetime.now(UTC),
    )
    fake_session = FakeSession(user)

    async def override_session() -> AsyncIterator[FakeSession]:
        yield fake_session

    app.dependency_overrides[get_session] = override_session
    async def fake_object_url(object_key: str, expires_in: int) -> str:
        assert expires_in == 7 * 86400
        return f"https://cdn.example/{object_key}"

    monkeypatch.setattr(upload.oss_service, "get_object_url", fake_object_url)

    async def fake_metadata(_: str) -> dict[str, object]:
        return {"content_type": "image/png", "size_bytes": 1024}

    monkeypatch.setattr(upload.oss_service, "get_object_metadata", fake_metadata, raising=False)

    object_key = f"avatar/{user.id}/20260506/avatar.png"
    response = await client.post(
        "/api/upload/confirm",
        headers=auth_headers(user.id),
        json={"object_key": object_key, "size_bytes": 1024},
    )

    assert response.status_code == 200
    assert response.json()["avatar_url"] == f"https://cdn.example/{object_key}"
    assert user.avatar_url == object_key
    assert fake_session.committed is True


@pytest.mark.asyncio
async def test_avatar_confirm_accepts_extensionless_upload_when_metadata_is_image(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = User(
        id=uuid4(),
        phone="13800138000",
        nickname="老板",
        plan="free",
        created_at=datetime.now(UTC),
    )
    fake_session = FakeSession(user)

    async def override_session() -> AsyncIterator[FakeSession]:
        yield fake_session

    app.dependency_overrides[get_session] = override_session
    async def fake_object_url(object_key: str, expires_in: int) -> str:
        assert expires_in == 7 * 86400
        return f"https://cdn.example/{object_key}"

    monkeypatch.setattr(upload.oss_service, "get_object_url", fake_object_url)

    async def fake_metadata(_: str) -> dict[str, object]:
        return {"content_type": "image/png", "size_bytes": 1024}

    monkeypatch.setattr(upload.oss_service, "get_object_metadata", fake_metadata, raising=False)

    object_key = f"avatar/{user.id}/20260506/avatar"
    response = await client.post(
        "/api/upload/confirm",
        headers=auth_headers(user.id),
        json={"object_key": object_key, "size_bytes": 1024},
    )

    assert response.status_code == 200
    assert response.json()["avatar_url"] == f"https://cdn.example/{object_key}"
    assert user.avatar_url == object_key


@pytest.mark.asyncio
async def test_avatar_confirm_rejects_non_image_metadata_even_with_image_suffix(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = User(
        id=uuid4(),
        phone="13800138000",
        nickname="老板",
        plan="free",
        created_at=datetime.now(UTC),
    )

    async def override_session() -> AsyncIterator[FakeSession]:
        yield FakeSession(user)

    async def fake_metadata(_: str) -> dict[str, object]:
        return {"content_type": "text/plain", "size_bytes": 1024}

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(upload.oss_service, "get_object_metadata", fake_metadata, raising=False)

    response = await client.post(
        "/api/upload/confirm",
        headers=auth_headers(user.id),
        json={"object_key": f"avatar/{user.id}/20260506/avatar.png", "size_bytes": 1024},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_avatar_confirm_returns_not_found_when_metadata_probe_is_missing(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = User(
        id=uuid4(),
        phone="13800138000",
        nickname="老板",
        plan="free",
        created_at=datetime.now(UTC),
    )
    fake_session = FakeSession(user)

    async def override_session() -> AsyncIterator[FakeSession]:
        yield fake_session

    async def fake_metadata(_: str) -> None:
        return None

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(upload.oss_service, "get_object_metadata", fake_metadata, raising=False)

    response = await client.post(
        "/api/upload/confirm",
        headers=auth_headers(user.id),
        json={"object_key": f"avatar/{user.id}/20260506/missing.png", "size_bytes": 1024},
    )

    assert response.status_code == 404
    assert fake_session.committed is False


@pytest.mark.asyncio
async def test_profile_patch_rejects_untrusted_avatar_url(client: AsyncClient) -> None:
    user = User(
        id=uuid4(),
        phone="13800138000",
        nickname="老板",
        plan="free",
        created_at=datetime.now(UTC),
    )

    async def override_session() -> AsyncIterator[FakeSession]:
        yield FakeSession(user)

    app.dependency_overrides[get_session] = override_session

    response = await client.patch(
        "/api/profile/me",
        headers=auth_headers(user.id),
        json={"avatar_url": "https://evil.example/avatar.png"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_profile_backfills_default_avatar_style(client: AsyncClient) -> None:
    user = User(
        id=uuid4(),
        phone="13800138000",
        nickname="老板",
        plan="free",
        created_at=datetime.now(UTC),
    )
    fake_session = FakeSession(user)

    async def override_session() -> AsyncIterator[FakeSession]:
        yield fake_session

    app.dependency_overrides[get_session] = override_session

    response = await client.get("/api/profile/me", headers=auth_headers(user.id))

    assert response.status_code == 200
    assert response.json()["avatar_style"] in {
        "pixel-emerald",
        "pixel-amber",
        "pixel-violet",
        "pixel-cyan",
        "nft-rose",
        "nft-indigo",
        "nft-slate",
        "nft-gold",
    }
    assert fake_session.committed is True
