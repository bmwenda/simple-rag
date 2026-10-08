import hashlib
import mimetypes
from pathlib import Path

from .document_repository import DocumentRepository
from .domain import DocumentRecord, DocumentStatus


class DocumentRegistry:
    """Track document identity and ingestion state through a repository."""

    def __init__(self, database_path: Path) -> None:
        self._repository = DocumentRepository.for_sqlite_path(database_path)

    def register_source(
        self,
        source_path: Path,
        *,
        source_reference: str | None = None,
        display_name: str | None = None,
        content_type: str | None = None,
    ) -> DocumentRecord:
        resolved_path = source_path.resolve()
        return self._repository.register_source(
            source_reference=source_reference or str(resolved_path),
            display_name=display_name or resolved_path.name,
            content_type=(
                content_type
                or mimetypes.guess_type(resolved_path.name)[0]
                or "application/octet-stream"
            ),
            size_bytes=resolved_path.stat().st_size,
            checksum_sha256=_checksum(resolved_path),
        )

    def get(self, document_id: str) -> DocumentRecord:
        return self._repository.get(document_id)

    def mark_processing(self, document_id: str) -> DocumentRecord:
        return self._repository.set_status(document_id, DocumentStatus.PROCESSING)

    def mark_retry(self, document_id: str) -> DocumentRecord:
        return self._repository.mark_retry(document_id)

    def mark_ready(
        self,
        document_id: str,
        *,
        index_version: int,
        chunk_count: int,
    ) -> DocumentRecord:
        return self._repository.mark_ready(
            document_id, index_version=index_version, chunk_count=chunk_count
        )

    def mark_failed(self, document_id: str, error: Exception) -> DocumentRecord:
        return self._repository.mark_failed(document_id, type(error).__name__)


def _checksum(source_path: Path) -> str:
    digest = hashlib.sha256()
    with source_path.open("rb") as source_file:
        for block in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
