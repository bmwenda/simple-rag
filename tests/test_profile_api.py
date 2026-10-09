"""Contract checks for the first self-profile HTTP routes."""

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_repository
from src.api.main import app, create_app
from src.profile import DuplicateEmailError, Profile, ProfileNotFoundError

TOKEN = "a-secret-test-token-with-at-least-32-characters"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)


class FakeProfileRepository:
    def __init__(self) -> None:
        self.profile: Profile | None = Profile(
            id=1,
            email="owner@example.com",
            first_name="Ada",
            last_name=None,
            role="owner",
            created_at=NOW,
            updated_at=NOW,
        )
        self.read_count = 0
        self.closed = False

    def get_owner(self) -> Profile | None:
        self.read_count += 1
        return self.profile

    def update_profile(self, user_id: int, changes: dict[str, str | None]) -> Profile:
        assert user_id == 1
        assert self.profile is not None
        if changes.get("email") == "taken@example.com":
            raise DuplicateEmailError
        self.profile = Profile(
            id=self.profile.id,
            email=changes.get("email", self.profile.email) or self.profile.email,
            first_name=changes.get("first_name", self.profile.first_name),
            last_name=changes.get("last_name", self.profile.last_name),
            role=self.profile.role,
            created_at=self.profile.created_at,
            updated_at=NOW,
        )
        return self.profile

    def delete_profile(self, user_id: int) -> None:
        assert user_id == 1
        if self.profile is None:
            raise ProfileNotFoundError
        self.profile = None

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, FakeProfileRepository]]:
    monkeypatch.setenv("API_BEARER_TOKEN", TOKEN)
    repository = FakeProfileRepository()
    app.dependency_overrides[get_repository] = lambda: repository
    try:
        yield TestClient(app, raise_server_exceptions=False), repository
    finally:
        app.dependency_overrides.clear()


def test_get_me_returns_public_profile(api: tuple[TestClient, FakeProfileRepository]) -> None:
    client, _repository = api

    response = client.get("/v1/users/me", headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "email": "owner@example.com",
        "first_name": "Ada",
        "last_name": None,
        "role": "owner",
        "created_at": "2026-10-09T00:00:00+00:00",
        "updated_at": "2026-10-09T00:00:00+00:00",
    }


def test_app_factory_opens_and_closes_repository_during_lifespan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("API_BEARER_TOKEN", TOKEN)
    repository = FakeProfileRepository()
    calls = 0

    def repository_factory() -> FakeProfileRepository:
        nonlocal calls
        calls += 1
        return repository

    isolated_app = create_app(repository_factory)
    assert calls == 0

    with TestClient(isolated_app) as client:
        assert calls == 1
        assert client.get("/v1/users/me", headers=HEADERS).status_code == 200
        assert not repository.closed

    assert repository.closed


def test_patch_me_normalizes_email_and_updates_only_supplied_fields(
    api: tuple[TestClient, FakeProfileRepository],
) -> None:
    client, _repository = api

    response = client.patch(
        "/v1/users/me",
        headers=HEADERS,
        json={"email": "  Owner.New@Example.COM ", "last_name": " Lovelace "},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "owner.new@example.com"
    assert response.json()["first_name"] == "Ada"
    assert response.json()["last_name"] == "Lovelace"


def test_patch_me_rejects_duplicate_email(
    api: tuple[TestClient, FakeProfileRepository],
) -> None:
    client, _repository = api

    response = client.patch(
        "/v1/users/me", headers=HEADERS, json={"email": "Taken@Example.com"}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_conflict"


@pytest.mark.parametrize(
    "payload",
    [{}, {"email": None}, {"email": "invalid"}, {"user_id": 2}, {"first_name": 123}],
)
def test_patch_me_rejects_malformed_input(
    api: tuple[TestClient, FakeProfileRepository], payload: dict[str, object]
) -> None:
    client, _repository = api

    response = client.patch("/v1/users/me", headers=HEADERS, json=payload)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_delete_me_revokes_access_immediately(
    api: tuple[TestClient, FakeProfileRepository],
) -> None:
    client, repository = api

    response = client.delete("/v1/users/me", headers=HEADERS)

    assert response.status_code == 204
    assert response.content == b""
    assert repository.profile is None
    assert client.get("/v1/users/me", headers=HEADERS).status_code == 401
    assert client.patch(
        "/v1/users/me", headers=HEADERS, json={"first_name": "New"}
    ).status_code == 401


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}])
def test_missing_or_invalid_bearer_token_is_unauthorized(
    api: tuple[TestClient, FakeProfileRepository], headers: dict[str, str]
) -> None:
    client, repository = api

    response = client.get("/v1/users/me", headers=headers)

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "unauthorized", "message": "Invalid or missing credentials"}
    }
    assert repository.read_count == 0


def test_no_public_registration_or_id_based_access(
    api: tuple[TestClient, FakeProfileRepository],
) -> None:
    client, _repository = api

    assert client.post("/v1/users", json={"email": "other@example.com"}).status_code == 404
    assert client.delete("/v1/users/1", headers=HEADERS).status_code == 404


def test_unconfigured_bearer_token_is_unavailable(
    api: tuple[TestClient, FakeProfileRepository], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repository = api
    monkeypatch.setenv("API_BEARER_TOKEN", "short")

    response = client.get("/v1/users/me", headers=HEADERS)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert repository.read_count == 0


def test_malformed_json_is_a_bad_request(
    api: tuple[TestClient, FakeProfileRepository],
) -> None:
    client, _repository = api

    response = client.patch(
        "/v1/users/me",
        headers={**HEADERS, "Content-Type": "application/json"},
        content="{",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_backend_failures_are_sanitized(
    api: tuple[TestClient, FakeProfileRepository],
) -> None:
    client, repository = api

    def fail() -> Profile | None:
        raise RuntimeError("database password=hidden")

    repository.get_owner = fail  # type: ignore[method-assign]
    response = client.get("/v1/users/me", headers=HEADERS)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert "password" not in response.text
