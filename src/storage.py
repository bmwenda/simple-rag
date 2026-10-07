from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .domain import ConfigurationError


@dataclass(frozen=True)
class SourceObject:
    bucket: str
    key: str
    size_bytes: int
    content_type: str | None

    @property
    def uri(self) -> str:
        return f"s3://{self.bucket}/{self.key}"


class S3Client(Protocol):
    def head_object(self, **kwargs: object) -> dict[str, Any]: ...

    def download_fileobj(self, bucket: str, key: str, fileobj: object) -> None: ...


class S3DocumentStorage:
    """Read private source-bucket objects without buffering them in memory."""

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "",
        max_document_size_bytes: int,
        region: str | None = None,
        client: S3Client | None = None,
    ) -> None:
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._max_document_size_bytes = max_document_size_bytes
        self._client = client or _create_s3_client(region)

    def get_object(self, bucket: str, key: str) -> SourceObject:
        self._validate_location(bucket, key)
        response = self._client.head_object(Bucket=bucket, Key=key)
        size_bytes = response.get("ContentLength")
        if not isinstance(size_bytes, int) or size_bytes < 0:
            raise ValueError("S3 object has no valid content length")
        if size_bytes > self._max_document_size_bytes:
            raise ValueError("S3 object exceeds MAX_DOCUMENT_SIZE_BYTES")
        return SourceObject(
            bucket=bucket,
            key=key,
            size_bytes=size_bytes,
            content_type=_optional_string(response.get("ContentType")),
        )

    def download_to(self, source: SourceObject, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as output:
            self._client.download_fileobj(source.bucket, source.key, output)

    def _validate_location(self, bucket: str, key: str) -> None:
        if bucket != self._bucket:
            raise ValueError("S3 event bucket is not configured as a source bucket")
        if not key or key.endswith("/"):
            raise ValueError("S3 event does not identify a document object")
        if self._prefix and not key.startswith(f"{self._prefix}/"):
            raise ValueError("S3 object is outside S3_SOURCE_PREFIX")
        if Path(key).suffix.lower() not in {".pdf", ".txt"}:
            raise ValueError("Unsupported S3 document type")


def create_s3_document_storage(
    *,
    bucket: str | None,
    prefix: str,
    max_document_size_bytes: int,
    region: str | None,
) -> S3DocumentStorage:
    if not bucket:
        raise ConfigurationError("S3_SOURCE_BUCKET must be configured for S3 ingestion")
    return S3DocumentStorage(
        bucket=bucket,
        prefix=prefix,
        max_document_size_bytes=max_document_size_bytes,
        region=region,
    )


def _create_s3_client(region: str | None) -> S3Client:
    try:
        import boto3  # type: ignore[import-untyped]
    except ImportError as error:
        raise ConfigurationError("boto3 must be installed for S3 ingestion") from error
    return boto3.client("s3", region_name=region)


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None
