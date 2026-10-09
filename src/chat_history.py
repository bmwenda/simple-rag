"""Chat history records and request rules."""

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from .domain import Citation


class ChatNotFoundError(Exception):
    """A chat is absent, deleted, or owned by someone else."""


class InvalidChatError(Exception):
    """A chat request violates the public contract."""


class ArchivedChatError(Exception):
    """An archived chat cannot accept a new message."""


@dataclass(frozen=True)
class ChatRecord:
    id: int
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


@dataclass(frozen=True)
class ChatSummary:
    chat: ChatRecord
    latest_activity_at: datetime


@dataclass(frozen=True)
class MessageRecord:
    id: int
    speaker: str
    content: str
    created_at: datetime
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True)
class ChatPage:
    items: tuple[ChatSummary, ...]
    next_cursor: str | None


def normalize_content(content: str) -> str:
    value = content.strip()
    if not value:
        raise InvalidChatError("Content is required")
    return value


def normalize_title(title: str) -> str:
    value = " ".join(title.split())
    if not value:
        raise InvalidChatError("Title is required")
    if len(value) > 120:
        raise InvalidChatError("Title is too long")
    return value


def title_from_question(content: str) -> str:
    return normalize_title(content[:120])


def normalize_update(changes: dict[str, str]) -> dict[str, str]:
    if not changes or set(changes) - {"title", "status"}:
        raise InvalidChatError("Provide a title or status")
    normalized = dict(changes)
    if "title" in normalized:
        normalized["title"] = normalize_title(normalized["title"])
    if "status" in normalized and normalized["status"] not in {"active", "archived"}:
        raise InvalidChatError("Invalid chat status")
    return normalized


def encode_cursor(updated_at: datetime, chat_id: int) -> str:
    payload = json.dumps([updated_at.isoformat(), chat_id], separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        timestamp, chat_id = json.loads(raw)
        value = datetime.fromisoformat(timestamp)
        if value.tzinfo is None or type(chat_id) is not int or chat_id < 1:
            raise ValueError
        value = value.astimezone(timezone.utc)
        if encode_cursor(value, chat_id) != cursor:
            raise ValueError
        return value, chat_id
    except (ValueError, TypeError, UnicodeDecodeError, binascii.Error):
        raise InvalidChatError("Invalid cursor") from None
