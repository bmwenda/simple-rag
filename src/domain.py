from dataclasses import dataclass


class RAGError(Exception):
    """Base exception for expected application failures."""


class ConfigurationError(RAGError):
    """Raised when application configuration is invalid."""


class RetrievalError(RAGError):
    """Raised when context retrieval fails."""


class AnswerGenerationError(RAGError):
    """Raised when the language model cannot generate an answer."""


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
