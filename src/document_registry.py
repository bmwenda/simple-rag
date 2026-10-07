import hashlib
import mimetypes
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .domain import DocumentRecord, DocumentStatus


class DocumentRegistry:
    """Persist document identity and ingestion state for local ingestion."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def register_source(self, source_path: Path) -> DocumentRecord:
        source_path = source_path.resolve()
        checksum = _checksum(source_path)
        size_bytes = source_path.stat().st_size
        content_type = (
            mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
        )
        now = _timestamp()

        with self._connection() as connection:
            existing = connection.execute(
                "SELECT * FROM documents WHERE source_path = ?", (str(source_path),)
            ).fetchone()
            if existing is None:
                document_id = str(uuid.uuid4())
                connection.execute(
                    """
                    INSERT INTO documents (
                        document_id, source_path, display_name, content_type, size_bytes,
                        checksum_sha256, status, index_version, chunk_count, retry_count,
                        error_code, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, NULL, ?, ?)
                    """,
                    (
                        document_id,
                        str(source_path),
                        source_path.name,
                        content_type,
                        size_bytes,
                        checksum,
                        DocumentStatus.PENDING.value,
                        now,
                        now,
                    ),
                )
                return self.get(document_id, connection)

            record = _to_record(existing)
            if (
                record.status is DocumentStatus.READY
                and record.checksum_sha256 == checksum
            ):
                return record

            connection.execute(
                """
                UPDATE documents
                SET display_name = ?, content_type = ?, size_bytes = ?, checksum_sha256 = ?,
                    status = ?, retry_count = 0, error_code = NULL, updated_at = ?
                WHERE document_id = ?
                """,
                (
                    source_path.name,
                    content_type,
                    size_bytes,
                    checksum,
                    DocumentStatus.PENDING.value,
                    now,
                    record.document_id,
                ),
            )
            return self.get(record.document_id, connection)

    def get(
        self,
        document_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> DocumentRecord:
        if connection is not None:
            row = connection.execute(
                "SELECT * FROM documents WHERE document_id = ?", (document_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown document: {document_id}")
            return _to_record(row)

        with self._connection() as new_connection:
            return self.get(document_id, new_connection)

    def mark_processing(self, document_id: str) -> DocumentRecord:
        return self._update_status(document_id, DocumentStatus.PROCESSING)

    def mark_retry(self, document_id: str) -> DocumentRecord:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE documents
                SET retry_count = retry_count + 1, status = ?, updated_at = ?
                WHERE document_id = ?
                """,
                (DocumentStatus.PENDING.value, _timestamp(), document_id),
            )
            return self.get(document_id, connection)

    def mark_ready(
        self,
        document_id: str,
        *,
        index_version: int,
        chunk_count: int,
    ) -> DocumentRecord:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE documents
                SET status = ?, index_version = ?, chunk_count = ?, error_code = NULL,
                    updated_at = ?
                WHERE document_id = ?
                """,
                (
                    DocumentStatus.READY.value,
                    index_version,
                    chunk_count,
                    _timestamp(),
                    document_id,
                ),
            )
            return self.get(document_id, connection)

    def mark_failed(self, document_id: str, error: Exception) -> DocumentRecord:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE documents
                SET status = ?, error_code = ?, updated_at = ?
                WHERE document_id = ?
                """,
                (
                    DocumentStatus.FAILED.value,
                    type(error).__name__,
                    _timestamp(),
                    document_id,
                ),
            )
            return self.get(document_id, connection)

    def _update_status(
        self,
        document_id: str,
        status: DocumentStatus,
    ) -> DocumentRecord:
        with self._connection() as connection:
            connection.execute(
                "UPDATE documents SET status = ?, updated_at = ? WHERE document_id = ?",
                (status.value, _timestamp(), document_id),
            )
            return self.get(document_id, connection)

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    checksum_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL,
                    index_version INTEGER NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    retry_count INTEGER NOT NULL,
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection


def _checksum(source_path: Path) -> str:
    digest = hashlib.sha256()
    with source_path.open("rb") as source_file:
        for block in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_record(row: sqlite3.Row) -> DocumentRecord:
    return DocumentRecord(
        document_id=row["document_id"],
        source_path=row["source_path"],
        display_name=row["display_name"],
        content_type=row["content_type"],
        size_bytes=row["size_bytes"],
        checksum_sha256=row["checksum_sha256"],
        status=DocumentStatus(row["status"]),
        index_version=row["index_version"],
        chunk_count=row["chunk_count"],
        retry_count=row["retry_count"],
        error_code=row["error_code"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
