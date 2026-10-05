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
class ChatResponse:
    text: str
