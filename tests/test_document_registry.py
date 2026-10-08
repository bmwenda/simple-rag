import sqlite3
from pathlib import Path

import pytest

from src.document_registry import DocumentRegistry
from src.domain import DocumentStatus


def test_existing_sqlite_registry_remains_readable_and_writable(tmp_path: Path) -> None:
    database_path = tmp_path / "documents.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE documents (
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
        connection.execute(
            """
            INSERT INTO documents VALUES (
                'existing-id', '/sources/guide.txt', 'guide.txt', 'text/plain',
                5, 'checksum', 'ready', 2, 3, 1, NULL,
                '2026-10-01T09:00:00+00:00', '2026-10-01T09:01:00+00:00'
            )
            """
        )

    registry = DocumentRegistry(database_path)
    existing = registry.get("existing-id")
    assert existing.status is DocumentStatus.READY
    assert existing.index_version == 2
    assert existing.created_at.utcoffset().total_seconds() == 0

    failed = registry.mark_failed("existing-id", ValueError("bad input"))
    assert failed.error_code == "ValueError"
    assert DocumentRegistry(database_path).get("existing-id") == failed


def test_registry_rejects_unknown_document(tmp_path: Path) -> None:
    registry = DocumentRegistry(tmp_path / "documents.sqlite3")

    with pytest.raises(KeyError, match="Unknown document: missing-id"):
        registry.mark_processing("missing-id")
