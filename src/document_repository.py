"""SQLAlchemy persistence for the current document registry schema."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, select, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .database import create_database_engine
from .domain import ConfigurationError, DocumentRecord, DocumentStatus


class Base(DeclarativeBase):
    pass


class DocumentRow(Base):
    __tablename__ = "documents"

    document_id: Mapped[str] = mapped_column(String, primary_key=True)
    source_path: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    index_version: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentRepository:
    """Keep each registry operation in one database transaction."""

    def __init__(self, database_url: URL) -> None:
        engine: Engine | None = None
        try:
            engine = create_database_engine(database_url)
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                connection.execute(select(DocumentRow).limit(0))
        except (SQLAlchemyError, OSError, ImportError):
            if engine is not None:
                engine.dispose()
            raise ConfigurationError(
                "Document registry database is unavailable or schema is incompatible"
            ) from None
        assert engine is not None
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def register_source(
        self,
        *,
        source_reference: str,
        display_name: str,
        content_type: str,
        size_bytes: int,
        checksum_sha256: str,
    ) -> DocumentRecord:
        now = _timestamp()
        with self._sessions.begin() as session:
            row = session.scalar(
                select(DocumentRow).where(DocumentRow.source_path == source_reference)
            )
            if row is None:
                row = DocumentRow(
                    document_id=str(uuid.uuid4()),
                    source_path=source_reference,
                    display_name=display_name,
                    content_type=content_type,
                    size_bytes=size_bytes,
                    checksum_sha256=checksum_sha256,
                    status=DocumentStatus.PENDING.value,
                    index_version=0,
                    chunk_count=0,
                    retry_count=0,
                    error_code=None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            elif not (
                row.status == DocumentStatus.READY.value
                and row.checksum_sha256 == checksum_sha256
            ):
                row.display_name = display_name
                row.content_type = content_type
                row.size_bytes = size_bytes
                row.checksum_sha256 = checksum_sha256
                row.status = DocumentStatus.PENDING.value
                row.retry_count = 0
                row.error_code = None
                row.updated_at = now
            session.flush()
            return _to_record(row)

    def get(self, document_id: str) -> DocumentRecord:
        with self._sessions() as session:
            return _to_record(_get_row(session, document_id))

    def set_status(self, document_id: str, status: DocumentStatus) -> DocumentRecord:
        with self._sessions.begin() as session:
            row = _get_row(session, document_id)
            row.status = status.value
            row.updated_at = _timestamp()
            session.flush()
            return _to_record(row)

    def mark_retry(self, document_id: str) -> DocumentRecord:
        with self._sessions.begin() as session:
            row = _get_row(session, document_id)
            row.retry_count += 1
            row.status = DocumentStatus.PENDING.value
            row.updated_at = _timestamp()
            session.flush()
            return _to_record(row)

    def mark_ready(
        self, document_id: str, *, index_version: int, chunk_count: int
    ) -> DocumentRecord:
        with self._sessions.begin() as session:
            row = _get_row(session, document_id)
            row.status = DocumentStatus.READY.value
            row.index_version = index_version
            row.chunk_count = chunk_count
            row.error_code = None
            row.updated_at = _timestamp()
            session.flush()
            return _to_record(row)

    def mark_failed(self, document_id: str, error_code: str) -> DocumentRecord:
        with self._sessions.begin() as session:
            row = _get_row(session, document_id)
            row.status = DocumentStatus.FAILED.value
            row.error_code = error_code
            row.updated_at = _timestamp()
            session.flush()
            return _to_record(row)


def _get_row(session: Session, document_id: str) -> DocumentRow:
    row = session.get(DocumentRow, document_id)
    if row is None:
        raise KeyError(f"Unknown document: {document_id}")
    return row


def _timestamp() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_record(row: DocumentRow) -> DocumentRecord:
    return DocumentRecord(
        document_id=row.document_id,
        source_path=row.source_path,
        display_name=row.display_name,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        checksum_sha256=row.checksum_sha256,
        status=DocumentStatus(row.status),
        index_version=row.index_version,
        chunk_count=row.chunk_count,
        retry_count=row.retry_count,
        error_code=row.error_code,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
    )
