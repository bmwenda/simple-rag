from typing import Any

from .config import Settings
from .ingestion import DocumentIngestionService, create_ingestion_service
from .s3_events import s3_object_created_events
from .storage import S3DocumentStorage, create_s3_document_storage


class S3IngestionHandler:
    def __init__(
        self,
        service: DocumentIngestionService,
        storage: S3DocumentStorage,
    ) -> None:
        self._service = service
        self._storage = storage

    def handle(self, event: dict[str, object]) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for record in s3_object_created_events(event):
            result = self._service.ingest_s3_object(
                self._storage,
                bucket=record.bucket,
                key=record.key,
            )
            document = result.document
            results.append(
                {
                    "document_id": document.document_id,
                    "status": document.status.value,
                    "indexed": result.indexed,
                }
            )
        return results


def lambda_handler(
    event: dict[str, object],
    _context: object | None = None,
) -> dict[str, Any]:
    """AWS Lambda entrypoint for direct S3 or SQS-delivered S3 events."""
    settings = Settings.from_env()
    storage = create_s3_document_storage(
        bucket=settings.s3_source_bucket,
        prefix=settings.s3_source_prefix,
        max_document_size_bytes=settings.max_document_size_bytes,
        region=settings.aws_region,
    )
    results = S3IngestionHandler(create_ingestion_service(settings), storage).handle(event)
    return {"processed": len(results), "documents": results}
