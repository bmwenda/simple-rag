from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr

from .config import Settings
from .loader import load_and_chunk_sources


def embeddings(settings: Settings | None = None) -> OpenAIEmbeddings:
    settings = settings or Settings.from_env()
    return OpenAIEmbeddings(
        api_key=SecretStr(settings.openai_api_key),
        model=settings.embedding_model,
    )


def vector_store(settings: Settings | None = None) -> Chroma:
    settings = settings or Settings.from_env()
    return Chroma(
        embedding_function=embeddings(settings),
        collection_name=settings.chroma_collection,
        persist_directory=str(settings.chroma_directory),
    )


def save_documents(settings: Settings | None = None) -> list[str]:
    """Load source files and add their chunks to the persisted vector store."""

    settings = settings or Settings.from_env()
    chunks, chunk_ids, source_files = load_and_chunk_sources(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    vector_store(settings).add_documents(documents=chunks, ids=chunk_ids)
    return source_files
