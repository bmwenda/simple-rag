"""SQLAlchemy storage for owned chat history."""

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    and_,
    or_,
    select,
    text,
)
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship, sessionmaker

from .chat_history import (
    ArchivedChatError,
    ChatNotFoundError,
    ChatPage,
    ChatRecord,
    ChatSummary,
    MessageRecord,
    decode_cursor,
    encode_cursor,
)
from .database import create_database_engine
from .document_repository import Base
from .domain import Citation, ConfigurationError
from .profile_repository import UserRow


class ChatRow(Base):
    __tablename__ = "chats"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="ck_chats_status"),
        Index("ix_chats_owner_updated", "user_id", "updated_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user: Mapped[UserRow] = relationship()


class ChatMessageRow(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("speaker IN ('user', 'assistant')", name="ck_chat_messages_speaker"),
        Index("ix_chat_messages_chat_id", "chat_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    speaker: Mapped[str] = mapped_column(String(9), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChatCitationRow(Base):
    __tablename__ = "chat_citations"
    __table_args__ = (
        CheckConstraint("citation_number > 0", name="ck_chat_citations_number"),
        UniqueConstraint("message_id", "citation_number", name="uq_chat_citation_number"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False)
    citation_number: Mapped[int] = mapped_column(Integer, nullable=False)
    document_id: Mapped[str] = mapped_column(String, nullable=False)
    index_version: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    source_uri: Mapped[str] = mapped_column(String, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    excerpt: Mapped[str | None] = mapped_column(Text)


class SqlChatRepository:
    def __init__(self, database_url: URL, *, engine: Engine | None = None) -> None:
        owned_engine = engine is None
        engine = engine or create_database_engine(database_url)
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                connection.execute(select(ChatRow).limit(0))
                connection.execute(select(ChatMessageRow).limit(0))
                connection.execute(select(ChatCitationRow).limit(0))
        except (SQLAlchemyError, OSError, ImportError):
            if owned_engine:
                engine.dispose()
            raise ConfigurationError(
                "Chat database is unavailable or schema is incompatible"
            ) from None
        self._engine = engine
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def close(self) -> None:
        self._engine.dispose()

    def create_chat(self, user_id: int, title: str, content: str) -> tuple[ChatRecord, MessageRecord]:
        with self._sessions.begin() as session:
            _active_user(session, user_id)
            now = _timestamp()
            chat = ChatRow(
                user_id=user_id,
                title=title,
                status="active",
                created_at=now,
                updated_at=now,
            )
            session.add(chat)
            session.flush()
            message = ChatMessageRow(
                chat_id=chat.id, speaker="user", content=content, created_at=now
            )
            session.add(message)
            session.flush()
            return _to_chat(chat), _to_message(message)

    def add_assistant_message(
        self, user_id: int, chat_id: int, content: str, citations: tuple[Citation, ...]
    ) -> MessageRecord:
        with self._sessions.begin() as session:
            chat = _owned_chat(session, user_id, chat_id, lock=True)
            if chat.status != "active":
                raise ArchivedChatError
            now = _timestamp()
            message = ChatMessageRow(
                chat_id=chat.id, speaker="assistant", content=content, created_at=now
            )
            session.add(message)
            session.flush()
            for citation in citations:
                session.add(
                    ChatCitationRow(
                        message_id=message.id,
                        citation_number=citation.citation_id,
                        document_id=citation.document_id,
                        index_version=citation.index_version,
                        chunk_index=citation.chunk_index,
                        display_name=citation.display_name,
                        source_uri=citation.source_uri,
                        page_number=citation.page_number,
                        excerpt=citation.excerpt,
                    )
                )
            chat.updated_at = now
            return _to_message(message, citations)

    def list_chats(
        self, user_id: int, status: str | None, cursor: str | None, limit: int
    ) -> ChatPage:
        with self._sessions() as session:
            statement = (
                select(ChatRow)
                .join(UserRow)
                .where(
                    ChatRow.user_id == user_id,
                    ChatRow.deleted_at.is_(None),
                    UserRow.deleted_at.is_(None),
                )
            )
            if status is not None:
                statement = statement.where(ChatRow.status == status)
            if cursor is not None:
                updated_at, chat_id = decode_cursor(cursor)
                statement = statement.where(
                    or_(
                        ChatRow.updated_at < updated_at,
                        and_(ChatRow.updated_at == updated_at, ChatRow.id < chat_id),
                    )
                )
            rows = session.scalars(
                statement.order_by(ChatRow.updated_at.desc(), ChatRow.id.desc()).limit(limit + 1)
            ).all()
            items = tuple(
                ChatSummary(chat=_to_chat(row), latest_activity_at=_as_utc(row.updated_at))
                for row in rows[:limit]
            )
            next_cursor = (
                encode_cursor(items[-1].chat.updated_at, items[-1].chat.id)
                if len(rows) > limit
                else None
            )
            return ChatPage(items=items, next_cursor=next_cursor)

    def get_chat(self, user_id: int, chat_id: int) -> ChatRecord:
        with self._sessions() as session:
            return _to_chat(_owned_chat(session, user_id, chat_id))

    def update_chat(self, user_id: int, chat_id: int, changes: dict[str, str]) -> ChatRecord:
        with self._sessions.begin() as session:
            row = _owned_chat(session, user_id, chat_id, lock=True)
            now = _timestamp()
            if "title" in changes:
                row.title = changes["title"]
            if "status" in changes and changes["status"] != row.status:
                row.status = changes["status"]
                row.archived_at = now if row.status == "archived" else None
            row.updated_at = now
            session.flush()
            return _to_chat(row)

    def delete_chat(self, user_id: int, chat_id: int) -> None:
        with self._sessions.begin() as session:
            row = _owned_chat(session, user_id, chat_id, lock=True)
            now = _timestamp()
            row.deleted_at = now
            row.updated_at = now


def _active_user(session: Session, user_id: int) -> None:
    if session.scalar(
        select(UserRow.id).where(UserRow.id == user_id, UserRow.deleted_at.is_(None))
    ) is None:
        raise ChatNotFoundError


def _owned_chat(session: Session, user_id: int, chat_id: int, *, lock: bool = False) -> ChatRow:
    statement = (
        select(ChatRow)
        .join(UserRow)
        .where(
            ChatRow.id == chat_id,
            ChatRow.user_id == user_id,
            ChatRow.deleted_at.is_(None),
            UserRow.deleted_at.is_(None),
        )
    )
    if lock:
        statement = statement.with_for_update()
    row = session.scalar(statement)
    if row is None:
        raise ChatNotFoundError
    return row


def _timestamp() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_chat(row: ChatRow) -> ChatRecord:
    return ChatRecord(
        id=row.id,
        title=row.title,
        status=row.status,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        archived_at=_as_utc(row.archived_at) if row.archived_at else None,
    )


def _to_message(row: ChatMessageRow, citations: tuple[Citation, ...] = ()) -> MessageRecord:
    return MessageRecord(
        id=row.id,
        speaker=row.speaker,
        content=row.content,
        created_at=_as_utc(row.created_at),
        citations=citations,
    )
