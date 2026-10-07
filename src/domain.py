from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class RAGError(Exception):
    """Base exception for expected application failures."""


class ConfigurationError(RAGError):
    """Raised when application configuration is invalid."""


class RetrievalError(RAGError):
    """Raised when context retrieval fails."""


class AnswerGenerationError(RAGError):
    """Raised when the language model cannot generate an answer."""


class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    source_path: str
    display_name: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    status: DocumentStatus
    index_version: int
    chunk_count: int
    retry_count: int
    error_code: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class IngestionResult:
    document: DocumentRecord
    indexed: bool


@dataclass(frozen=True)
class RetrievedChunk:
    citation_id: int
    document_id: str
    display_name: str
    page_number: int | None
    chunk_index: int
    text: str
    relevance_score: float


@dataclass(frozen=True)
class Citation:
    citation_id: int
    document_id: str
    display_name: str
    page_number: int | None
    chunk_index: int
    excerpt: str


@dataclass(frozen=True)
class Answer:
    text: str
    citations: tuple[Citation, ...]
