"""Stateful fakes for service tests that do not need a database."""

import hashlib
import mimetypes
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from src.domain import DocumentRecord, DocumentStatus


class FakeDocumentRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, DocumentRecord] = {}
        self._by_source: dict[str, str] = {}

    def register_source(
        self,
        source_path: Path,
        *,
        source_reference: str | None = None,
        display_name: str | None = None,
        content_type: str | None = None,
    ) -> DocumentRecord:
        resolved_path = source_path.resolve()
        reference = source_reference or str(resolved_path)
        checksum = hashlib.sha256(resolved_path.read_bytes()).hexdigest()
        existing_id = self._by_source.get(reference)
        now = datetime.now(timezone.utc)
        if existing_id is not None:
            existing = self._by_id[existing_id]
            if (
                existing.status is DocumentStatus.READY
                and existing.checksum_sha256 == checksum
            ):
                return existing
            record = replace(
                existing,
                display_name=display_name or resolved_path.name,
                content_type=content_type
                or mimetypes.guess_type(resolved_path.name)[0]
                or "application/octet-stream",
                size_bytes=resolved_path.stat().st_size,
                checksum_sha256=checksum,
                status=DocumentStatus.PENDING,
                retry_count=0,
                error_code=None,
                updated_at=now,
            )
        else:
            document_id = f"document-{len(self._by_id) + 1}"
            record = DocumentRecord(
                document_id=document_id,
                source_path=reference,
                display_name=display_name or resolved_path.name,
                content_type=content_type
                or mimetypes.guess_type(resolved_path.name)[0]
                or "application/octet-stream",
                size_bytes=resolved_path.stat().st_size,
                checksum_sha256=checksum,
                status=DocumentStatus.PENDING,
                index_version=0,
                chunk_count=0,
                retry_count=0,
                error_code=None,
                created_at=now,
                updated_at=now,
            )
            self._by_source[reference] = document_id
        return self._save(record)

    def get(self, document_id: str) -> DocumentRecord:
        return self._by_id[document_id]

    def mark_processing(self, document_id: str) -> DocumentRecord:
        return self._save(
            replace(
                self.get(document_id),
                status=DocumentStatus.PROCESSING,
                updated_at=datetime.now(timezone.utc),
            )
        )

    def mark_retry(self, document_id: str) -> DocumentRecord:
        record = self.get(document_id)
        return self._save(
            replace(
                record,
                status=DocumentStatus.PENDING,
                retry_count=record.retry_count + 1,
                updated_at=datetime.now(timezone.utc),
            )
        )

    def mark_ready(
        self, document_id: str, *, index_version: int, chunk_count: int
    ) -> DocumentRecord:
        return self._save(
            replace(
                self.get(document_id),
                status=DocumentStatus.READY,
                index_version=index_version,
                chunk_count=chunk_count,
                error_code=None,
                updated_at=datetime.now(timezone.utc),
            )
        )

    def mark_failed(self, document_id: str, error: Exception) -> DocumentRecord:
        return self._save(
            replace(
                self.get(document_id),
                status=DocumentStatus.FAILED,
                error_code=type(error).__name__,
                updated_at=datetime.now(timezone.utc),
            )
        )

    def _save(self, record: DocumentRecord) -> DocumentRecord:
        self._by_id[record.document_id] = record
        return record
