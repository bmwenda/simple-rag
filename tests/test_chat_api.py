"""Chat collection HTTP contract backed by an isolated SQL database."""

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.api.dependencies import get_answerer, get_repository
from src.api.main import create_app
from src.chat_history import ArchivedChatError, ChatNotFoundError
from src.chat_repository import (
    ChatCitationRow,
    ChatMessageRow,
    ChatRow,
    SqlChatRepository,
)
from src.document_repository import Base
from src.domain import Answer, AnswerGenerationError, Citation
from src.profile_repository import RoleRow, UserRow
from tests.test_profile_api import FakeProfileRepository

TOKEN = "a-secret-test-token-with-at-least-32-characters"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)


class FakeAnswerer:
    def __init__(self) -> None:
        self.error: Exception | None = None

    def answer(self, query: str) -> Answer:
        if self.error:
            raise self.error
        return Answer(
            text="Read the policy [1].",
            citations=(
                Citation(
                    citation_id=1,
                    document_id="policy",
                    display_name="policy.pdf",
                    page_number=2,
                    chunk_index=4,
                    excerpt="Read the policy",
                    index_version=3,
                    source_uri="s3://private/policy.pdf",
                ),
            ),
        )


@pytest.fixture
def chat_api(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer]]:
    monkeypatch.setenv("API_BEARER_TOKEN", TOKEN)
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(RoleRow(id=1, name="owner"))
        session.add_all(
            [
                UserRow(
                    id=user_id,
                    email=f"user{user_id}@example.com",
                    role_id=1,
                    created_at=NOW,
                    updated_at=NOW,
                )
                for user_id in (1, 2)
            ]
        )
    repository = SqlChatRepository(make_url("sqlite+pysqlite:///:memory:"), engine=engine)
    answerer = FakeAnswerer()
    app = create_app(
        repository_factory=FakeProfileRepository,
        chat_repository_factory=lambda: repository,
    )
    app.dependency_overrides[get_repository] = FakeProfileRepository
    app.dependency_overrides[get_answerer] = lambda: answerer
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, repository, engine, answerer
    app.dependency_overrides.clear()


def test_create_read_update_archive_reactivate_and_delete(
    chat_api: tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer],
) -> None:
    client, repository, engine, _answerer = chat_api
    response = client.post("/v1/chats", headers=HEADERS, json={"content": "  First question?  "})
    assert response.status_code == 201
    created = response.json()
    chat_id = created["chat"]["id"]
    assert created["chat"]["title"] == "First question?"
    assert created["chat"]["status"] == "active"
    assert created["user_message"]["content"] == "First question?"
    assert created["user_message"]["citations"] == []
    assert created["assistant_message"]["citations"] == [
        {
            "citation_number": 1,
            "document_id": "policy",
            "index_version": 3,
            "chunk_index": 4,
            "display_name": "policy.pdf",
            "page_number": 2,
            "excerpt": "Read the policy",
        }
    ]
    assert "source_uri" not in response.text
    with Session(engine) as session:
        assert session.scalar(select(ChatCitationRow.source_uri)) == "s3://private/policy.pdf"
        assert session.scalars(
            select(ChatMessageRow.speaker).order_by(ChatMessageRow.id)
        ).all() == ["user", "assistant"]

    assert client.get(f"/v1/chats/{chat_id}", headers=HEADERS).status_code == 200
    archived = client.patch(
        f"/v1/chats/{chat_id}",
        headers=HEADERS,
        json={"title": "Renamed", "status": "archived"},
    )
    assert archived.status_code == 200
    assert archived.json()["title"] == "Renamed"
    assert archived.json()["archived_at"] is not None
    assert client.get("/v1/chats?status=archived", headers=HEADERS).json()["items"][0]["id"] == chat_id
    assert client.get(f"/v1/chats/{chat_id}", headers=HEADERS).status_code == 200
    with pytest.raises(ArchivedChatError):
        repository.add_assistant_message(1, chat_id, "late", ())

    active = client.patch(f"/v1/chats/{chat_id}", headers=HEADERS, json={"status": "active"})
    assert active.status_code == 200
    assert active.json()["archived_at"] is None
    assert client.delete(f"/v1/chats/{chat_id}", headers=HEADERS).status_code == 204
    assert client.get(f"/v1/chats/{chat_id}", headers=HEADERS).status_code == 404
    assert client.patch(f"/v1/chats/{chat_id}", headers=HEADERS, json={"title": "No"}).status_code == 404
    assert client.get("/v1/chats", headers=HEADERS).json()["items"] == []
    with Session(engine) as session:
        assert session.get(ChatRow, chat_id).deleted_at is not None  # type: ignore[union-attr]


def test_list_uses_stable_cursor_and_status_filter(
    chat_api: tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer],
) -> None:
    client, _repository, _engine, _answerer = chat_api
    ids = [
        client.post("/v1/chats", headers=HEADERS, json={"content": str(index)}).json()["chat"]["id"]
        for index in range(3)
    ]
    first = client.get("/v1/chats?limit=2", headers=HEADERS).json()
    assert [item["id"] for item in first["items"]] == ids[:0:-1]
    assert first["next_cursor"]
    second = client.get(
        "/v1/chats", headers=HEADERS, params={"limit": 2, "cursor": first["next_cursor"]}
    ).json()
    assert [item["id"] for item in second["items"]] == ids[:1]
    assert second["next_cursor"] is None
    client.patch(f"/v1/chats/{ids[0]}", headers=HEADERS, json={"status": "archived"})
    assert [item["id"] for item in client.get("/v1/chats?status=archived", headers=HEADERS).json()["items"]] == [ids[0]]
    assert len(client.get("/v1/chats?status=active", headers=HEADERS).json()["items"]) == 2


def test_list_defaults_to_twenty_and_allows_one_hundred(
    chat_api: tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer],
) -> None:
    client, repository, _engine, _answerer = chat_api
    for index in range(21):
        repository.create_chat(1, f"Title {index}", f"Question {index}")

    default_page = client.get("/v1/chats", headers=HEADERS).json()
    assert len(default_page["items"]) == 20
    assert default_page["next_cursor"] is not None
    assert len(client.get("/v1/chats?limit=100", headers=HEADERS).json()["items"]) == 21


def test_ownership_and_deleted_user_are_hidden(
    chat_api: tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer],
) -> None:
    client, repository, engine, _answerer = chat_api
    foreign_chat, _ = repository.create_chat(2, "Private", "Question")
    url = f"/v1/chats/{foreign_chat.id}"
    for method in (client.get, client.patch, client.delete):
        kwargs = {"json": {"title": "Wrong"}} if method == client.patch else {}
        response = method(url, headers=HEADERS, **kwargs)
        assert response.status_code == 404
    assert client.get("/v1/chats", headers=HEADERS).json()["items"] == []

    own = client.post("/v1/chats", headers=HEADERS, json={"content": "Mine"}).json()["chat"]["id"]
    with Session(engine) as session, session.begin():
        owner = session.get(UserRow, 1)
        assert owner is not None
        owner.deleted_at = NOW
    with pytest.raises(ChatNotFoundError):
        repository.get_chat(1, own)
    assert client.get(url, headers=HEADERS).status_code == 404
    assert client.get("/v1/chats", headers=HEADERS).json()["items"] == []


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("post", "/v1/chats", {"content": "   "}),
        ("post", "/v1/chats", {"content": "Question", "user_id": 2}),
        ("patch", "/v1/chats/1", {}),
        ("patch", "/v1/chats/1", {"title": " "}),
        ("patch", "/v1/chats/1", {"status": "deleted"}),
    ],
)
def test_invalid_chat_requests_return_400(
    chat_api: tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer],
    method: str,
    path: str,
    payload: dict[str, object],
) -> None:
    client, _repository, _engine, _answerer = chat_api
    response = getattr(client, method)(path, headers=HEADERS, json=payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "status=deleted", "cursor=bad!"])
def test_invalid_list_query_returns_400(
    chat_api: tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer], query: str
) -> None:
    client, _repository, _engine, _answerer = chat_api
    response = client.get(f"/v1/chats?{query}", headers=HEADERS)
    assert response.status_code == 400


def test_generation_failure_is_sanitized_and_keeps_user_message(
    chat_api: tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer],
) -> None:
    client, _repository, engine, answerer = chat_api
    answerer.error = AnswerGenerationError("private key=secret")
    response = client.post("/v1/chats", headers=HEADERS, json={"content": "Question"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert "secret" not in response.text
    with Session(engine) as session:
        assert session.scalars(select(ChatMessageRow.speaker)).all() == ["user"]
        assert session.scalar(select(ChatRow.id)) is not None


def test_storage_failure_is_sanitized(
    chat_api: tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, repository, _engine, _answerer = chat_api

    def fail(_user_id: int, _status: str | None, _cursor: str | None, _limit: int) -> None:
        raise RuntimeError("database password=hidden")

    monkeypatch.setattr(repository, "list_chats", fail)
    response = client.get("/v1/chats", headers=HEADERS)
    assert response.status_code == 503
    assert "password" not in response.text


def test_missing_credentials_rejected_before_chat_access(
    chat_api: tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer],
) -> None:
    client, _repository, _engine, _answerer = chat_api
    response = client.get("/v1/chats")
    assert response.status_code == 401
