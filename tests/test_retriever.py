import pytest
from langchain_core.documents import Document

from src.domain import RetrievalError
from src.retriever import format_context, retrieve_documents


class FakeRetriever:
    def __init__(self, documents: list[Document] | None = None, error: Exception | None = None):
        self.documents = documents or []
        self.error = error

    def invoke(self, query: str, config=None, **kwargs) -> list[Document]:
        if self.error:
            raise self.error
        return self.documents


def test_format_context_includes_source_and_content() -> None:
    documents = [
        Document(
            page_content="Employees receive annual leave.",
            metadata={"source": "/documents/policies.txt"},
        )
    ]

    assert format_context(documents) == (
        "[Source: policies.txt]\nEmployees receive annual leave."
    )


def test_format_context_handles_no_results() -> None:
    assert format_context([]) == "No relevant documents were found."


def test_retrieve_documents_uses_injected_retriever() -> None:
    retriever = FakeRetriever(
        [Document(page_content="Context", metadata={"source": "guide.txt"})]
    )

    assert retrieve_documents("question", retriever=retriever) == (
        "[Source: guide.txt]\nContext"
    )


def test_retrieve_documents_wraps_failures() -> None:
    with pytest.raises(RetrievalError, match="Document retrieval failed"):
        retrieve_documents("question", retriever=FakeRetriever(error=OSError()))
