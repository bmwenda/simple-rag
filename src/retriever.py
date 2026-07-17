import os

from functools import lru_cache
from .embedding import vector_store

RETRIEVAL_COUNT = 4


@lru_cache(maxsize=1)
def get_retriever():
    """Return a retriever backed by the persisted Chroma collection."""
    return vector_store().as_retriever(
        search_type="similarity",
        search_kwargs={"k": RETRIEVAL_COUNT},
    )


def retrieve_documents(query: str) -> str:
    """Retrieve relevant chunks for a query and format them with source attribution."""
    retriever = get_retriever()

    try:
        retrieved_docs = retriever.invoke(query)
    except Exception as exc:
        raise RuntimeError(f"Retrieval failed for query: {query!r}") from exc

    if not retrieved_docs:
        return "No relevant documents were found."

    return "\n\n".join(
        f"[Source: {os.path.basename(doc.metadata.get('source', 'unknown'))}]\n{doc.page_content}"
        for doc in retrieved_docs
    )
