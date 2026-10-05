import os
from functools import lru_cache
from typing import Any, Protocol

from langchain_core.documents import Document
from langchain_core.runnables import RunnableConfig

from .config import Settings
from .domain import RetrievalError
from .embedding import vector_store


class Retriever(Protocol):
    def invoke(
        self,
        input: str,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> list[Document]: ...


@lru_cache(maxsize=1)
def _get_retriever(settings: Settings) -> Retriever:
    """Return a retriever backed by the persisted Chroma collection."""
    return vector_store(settings).as_retriever(
        search_type="similarity",
        search_kwargs={"k": settings.retrieval_count},
    )


def get_retriever(settings: Settings | None = None) -> Retriever:
    return _get_retriever(settings or Settings.from_env())


def format_context(documents: list[Document]) -> str:
    if not documents:
        return "No relevant documents were found."

    return "\n\n".join(
        f"[Source: {os.path.basename(doc.metadata.get('source', 'unknown'))}]\n"
        f"{doc.page_content}"
        for doc in documents
    )


def retrieve_documents(
    query: str,
    retriever: Retriever | None = None,
    settings: Settings | None = None,
) -> str:
    """Retrieve relevant chunks for a query and format them with source attribution."""
    retriever = retriever or get_retriever(settings)

    try:
        retrieved_docs = retriever.invoke(query)
    except Exception as exc:
        raise RetrievalError("Document retrieval failed") from exc

    return format_context(retrieved_docs)
