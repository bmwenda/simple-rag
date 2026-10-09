"""Chat collection HTTP contract backed by an isolated SQL database."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.api.dependencies import get_answerer, get_repository
from src.api.main import create_app
from src.chat_history import (
    ArchivedChatError,
    ChatBusyError,
    ChatNotFoundError,
    MessageRecord,
)
from src.chat_repository import (
    ChatCitationRow,
    ChatMessageRow,
    ChatRow,
    SqlChatRepository,
)
from src.document_repository import Base
from src.domain import Answer, AnswerGenerationError, Citation, RetrievalError
from src.profile_repository import RoleRow, UserRow
from tests.test_profile_api import FakeProfileRepository

TOKEN = "a-secret-test-token-with-at-least-32-characters"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)


class FakeAnswerer:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.history: tuple[MessageRecord, ...] = ()

    def answer(self, query: str, history: tuple[MessageRecord, ...] = ()) -> Answer:
        self.history = history
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
    tmp_path: Path,
) -> Iterator[tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer]]:
    monkeypatch.setenv("API_BEARER_TOKEN", TOKEN)
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'chat.db'}",
        connect_args={"check_same_thread": False},
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
    repository = SqlChatRepository(engine.url, engine=engine)
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


def test_followup_messages_are_chronological_and_keep_citation_snapshots(
    chat_api: tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer],
) -> None:
    client, _repository, engine, answerer = chat_api
    chat_id = client.post(
        "/v1/chats", headers=HEADERS, json={"content": "First question"}
    ).json()["chat"]["id"]
    response = client.post(
        f"/v1/chats/{chat_id}/messages",
        headers=HEADERS,
        json={"content": "  Follow up?  "},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["user_message"]["content"] == "Follow up?"
    assert body["user_message"]["citations"] == []
    assert body["assistant_message"]["citations"][0]["index_version"] == 3
    assert "source_uri" not in response.text
    assert [message.content for message in answerer.history] == [
        "First question",
        "Read the policy [1].",
    ]

    url = f"/v1/chats/{chat_id}/messages"
    first = client.get(url, headers=HEADERS, params={"limit": 2}).json()
    assert [item["speaker"] for item in first["items"]] == ["user", "assistant"]
    assert first["next_cursor"] is not None
    second = client.get(
        url, headers=HEADERS, params={"limit": 2, "cursor": first["next_cursor"]}
    ).json()
    assert [item["speaker"] for item in second["items"]] == ["user", "assistant"]
    assert second["next_cursor"] is None
    assert second["items"][1]["citations"][0]["document_id"] == "policy"
    assert "s3://private" not in str(second)
    with Session(engine) as session:
        snapshots = session.scalars(
            select(ChatCitationRow).order_by(ChatCitationRow.message_id)
        ).all()
        assert len(snapshots) == 2
        assert snapshots[1].source_uri == "s3://private/policy.pdf"


def test_message_list_defaults_to_twenty_and_caps_at_one_hundred(
    chat_api: tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer],
) -> None:
    client, repository, engine, _answerer = chat_api
    chat, _ = repository.create_chat(1, "Many", "First")
    with Session(engine) as session, session.begin():
        session.add_all(
            ChatMessageRow(chat_id=chat.id, speaker="user", content=str(index), created_at=NOW)
            for index in range(100)
        )
    url = f"/v1/chats/{chat.id}/messages"
    default = client.get(url, headers=HEADERS).json()
    assert len(default["items"]) == 20
    assert default["next_cursor"] is not None
    assert len(client.get(url, headers=HEADERS, params={"limit": 100}).json()["items"]) == 100
    assert client.get(url, headers=HEADERS, params={"limit": 101}).status_code == 400


def test_message_routes_hide_foreign_deleted_and_archived_chats(
    chat_api: tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer],
) -> None:
    client, repository, _engine, _answerer = chat_api
    foreign, _ = repository.create_chat(2, "Private", "Question")
    foreign_url = f"/v1/chats/{foreign.id}/messages"
    assert client.get(foreign_url, headers=HEADERS).status_code == 404
    assert client.post(foreign_url, headers=HEADERS, json={"content": "No"}).status_code == 404

    chat, _ = repository.create_chat(1, "Own", "Question")
    url = f"/v1/chats/{chat.id}/messages"
    repository.update_chat(1, chat.id, {"status": "archived"})
    assert client.get(url, headers=HEADERS).status_code == 200
    conflict = client.post(url, headers=HEADERS, json={"content": "Later"})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "chat_archived"
    repository.update_chat(1, chat.id, {"status": "active"})
    assert client.post(url, headers=HEADERS, json={"content": "Later"}).status_code == 201
    repository.delete_chat(1, chat.id)
    assert client.get(url, headers=HEADERS).status_code == 404
    assert client.post(url, headers=HEADERS, json={"content": "Again"}).status_code == 404


def test_message_cursor_is_bound_to_its_chat_and_request_is_validated(
    chat_api: tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer],
) -> None:
    client, repository, _engine, _answerer = chat_api
    first_chat, _ = repository.create_chat(1, "First", "One")
    second_chat, _ = repository.create_chat(1, "Second", "Two")
    cursor = client.get(
        f"/v1/chats/{first_chat.id}/messages", headers=HEADERS, params={"limit": 1}
    ).json()["next_cursor"]
    assert cursor is None  # A single message has no next page.
    repository.add_assistant_message(1, first_chat.id, "Answer", ())
    cursor = client.get(
        f"/v1/chats/{first_chat.id}/messages", headers=HEADERS, params={"limit": 1}
    ).json()["next_cursor"]
    assert cursor is not None
    assert client.get(
        f"/v1/chats/{second_chat.id}/messages",
        headers=HEADERS,
        params={"cursor": cursor},
    ).status_code == 400
    assert client.get(
        f"/v1/chats/{first_chat.id}/messages", headers=HEADERS, params={"cursor": "bad!"}
    ).status_code == 400
    assert client.post(
        f"/v1/chats/{first_chat.id}/messages", headers=HEADERS, json={"content": "  "}
    ).status_code == 400


@pytest.mark.parametrize("failure_type", [AnswerGenerationError, RetrievalError])
def test_failed_followup_keeps_user_message_and_releases_claim(
    chat_api: tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer],
    failure_type: type[Exception],
) -> None:
    client, _repository, _engine, answerer = chat_api
    chat_id = client.post(
        "/v1/chats", headers=HEADERS, json={"content": "First"}
    ).json()["chat"]["id"]
    answerer.error = failure_type("private key=secret")
    url = f"/v1/chats/{chat_id}/messages"
    failure = client.post(url, headers=HEADERS, json={"content": "Second"})
    assert failure.status_code == 503
    assert "secret" not in failure.text
    messages = client.get(url, headers=HEADERS).json()["items"]
    assert [item["speaker"] for item in messages] == ["user", "assistant", "user"]
    answerer.error = None
    assert client.post(url, headers=HEADERS, json={"content": "Third"}).status_code == 201


def test_followup_uses_only_recent_history(
    chat_api: tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer],
) -> None:
    client, repository, engine, answerer = chat_api
    chat, _ = repository.create_chat(1, "Long history", "Oldest")
    with Session(engine) as session, session.begin():
        session.add_all(
            ChatMessageRow(chat_id=chat.id, speaker="user", content=str(index), created_at=NOW)
            for index in range(20)
        )
    response = client.post(
        f"/v1/chats/{chat.id}/messages", headers=HEADERS, json={"content": "Next"}
    )
    assert response.status_code == 201
    assert len(answerer.history) == 12
    assert answerer.history[0].content == "8"
    assert answerer.history[-1].content == "19"


def test_concurrent_followup_is_rejected_while_generation_runs(
    chat_api: tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _repository, _engine, answerer = chat_api
    chat_id = client.post(
        "/v1/chats", headers=HEADERS, json={"content": "First"}
    ).json()["chat"]["id"]
    started = Event()
    release = Event()
    original_answer = answerer.answer

    def block_answer(query: str, history: tuple[MessageRecord, ...] = ()) -> Answer:
        if history:
            started.set()
            assert release.wait(timeout=5)
        return original_answer(query, history)

    monkeypatch.setattr(answerer, "answer", block_answer)
    url = f"/v1/chats/{chat_id}/messages"
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(
            client.post, url, headers=HEADERS, json={"content": "One more"}
        )
        assert started.wait(timeout=5)
        try:
            second = client.post(url, headers=HEADERS, json={"content": "Competing"})
            assert second.status_code == 409
            assert second.json()["error"]["code"] == "chat_busy"
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 201
    contents = [
        item["content"] for item in client.get(url, headers=HEADERS).json()["items"]
    ]
    assert "Competing" not in contents


def test_first_answer_claim_blocks_followup_until_creation_finishes(
    chat_api: tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _repository, _engine, answerer = chat_api
    started = Event()
    release = Event()
    original_answer = answerer.answer

    def block_first(query: str, history: tuple[MessageRecord, ...] = ()) -> Answer:
        if query == "First":
            started.set()
            assert release.wait(timeout=5)
        return original_answer(query, history)

    monkeypatch.setattr(answerer, "answer", block_first)
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(
            client.post, "/v1/chats", headers=HEADERS, json={"content": "First"}
        )
        assert started.wait(timeout=5)
        try:
            chat_id = client.get("/v1/chats", headers=HEADERS).json()["items"][0]["id"]
            conflict = client.post(
                f"/v1/chats/{chat_id}/messages",
                headers=HEADERS,
                json={"content": "Too early"},
            )
            assert conflict.status_code == 409
            assert conflict.json()["error"]["code"] == "chat_busy"
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 201


def test_expired_claim_can_be_replaced_without_accepting_late_answer(
    chat_api: tuple[TestClient, SqlChatRepository, Engine, FakeAnswerer],
) -> None:
    _client, repository, engine, _answerer = chat_api
    chat, _ = repository.create_chat(1, "Recover", "First")
    old = repository.begin_followup(1, chat.id, "Old question", 12)
    with Session(engine) as session, session.begin():
        row = session.get(ChatRow, chat.id)
        assert row is not None
        row.generation_started_at = datetime.now(timezone.utc) - timedelta(minutes=6)
    current = repository.begin_followup(1, chat.id, "New question", 12)
    with pytest.raises(ChatBusyError):
        repository.complete_followup(1, chat.id, old.token, "Late answer", ())
    repository.release_followup(chat.id, old.token)
    with Session(engine) as session:
        row = session.get(ChatRow, chat.id)
        assert row is not None
        assert row.generation_token == current.token
    repository.complete_followup(1, chat.id, current.token, "Current answer", ())
