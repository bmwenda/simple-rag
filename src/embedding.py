import os

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr

from .loader import load_and_chunk_sources

load_dotenv()


def embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        api_key=SecretStr(_get_required_env("OPENAI_API_KEY")),
        model="text-embedding-3-large"
    )

def vector_store() -> Chroma:
    return Chroma(
        embedding_function=embeddings(),
        collection_name="rag-documents",
        persist_directory="./chroma_db"
    )

def save_documents() -> list[str]:
    """Load source files and add their chunks to the persisted vector store."""

    chunks, chunk_ids, source_files = load_and_chunk_sources()
    vector_store().add_documents(documents=chunks, ids=chunk_ids)
    return source_files


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
