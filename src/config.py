import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from .domain import ConfigurationError


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = field(repr=False)
    openai_model: str
    embedding_model: str = "text-embedding-3-large"
    chroma_collection: str = "rag-documents"
    chroma_directory: Path = Path("chroma_db")
    retrieval_count: int = 4
    chunk_size: int = 1000
    chunk_overlap: int = 200

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        settings = cls(
            openai_api_key=_required_env("OPENAI_API_KEY"),
            openai_model=_required_env("OPENAI_MODEL"),
            embedding_model=os.getenv(
                "OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"
            ),
            chroma_collection=os.getenv("CHROMA_COLLECTION", "rag-documents"),
            chroma_directory=Path(os.getenv("CHROMA_DIRECTORY", "chroma_db")),
            retrieval_count=_integer_env("RETRIEVAL_COUNT", 4),
            chunk_size=_integer_env("CHUNK_SIZE", 1000),
            chunk_overlap=_integer_env("CHUNK_OVERLAP", 200),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.retrieval_count < 1:
            raise ConfigurationError("RETRIEVAL_COUNT must be at least 1")
        if self.chunk_size < 1:
            raise ConfigurationError("CHUNK_SIZE must be at least 1")
        if self.chunk_overlap < 0:
            raise ConfigurationError("CHUNK_OVERLAP cannot be negative")
        if self.chunk_overlap >= self.chunk_size:
            raise ConfigurationError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value


def _integer_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
