from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from src.chat import ABSTENTION_MESSAGE, ChatService, build_answer, format_context
from src.chat_history import MessageRecord
from src.domain import AnswerGenerationError, RetrievedChunk


@dataclass
class FakeMessage:
    text: str


class FakeChain:
    def __init__(self, response: str = "An answer [1]", error: Exception | None = None):
        self.response = response
        self.error = error
        self.input: dict[str, str] | None = None
        self.call_count = 0

    def invoke(self, input: dict[str, str]) -> FakeMessage:
        self.call_count += 1
        self.input = input
        if self.error:
            raise self.error
        return FakeMessage(self.response)


def chunk(
    citation_id: int = 1,
    *,
    page_number: int | None = 3,
    chunk_index: int = 0,
) -> RetrievedChunk:
    return RetrievedChunk(
        citation_id=citation_id,
        document_id="policies_pdf",
        display_name="policies.pdf",
        page_number=page_number,
        chunk_index=chunk_index,
        text=f"Context {citation_id}",
        relevance_score=0.9,
    )


def test_answer_passes_numbered_context_to_chain() -> None:
    chain = FakeChain(response="Use the handbook [1].")
    service = ChatService(chain=chain, retrieve=lambda query: [chunk()])

    answer = service.answer("Where is the policy?")

    assert answer.text == "Use the handbook [1]."
    assert [citation.citation_id for citation in answer.citations] == [1]
    assert chain.input == {
        "context": "[1] Source: policies.pdf, page 3\nContext 1",
        "query": "Where is the policy?",
        "history": "",
    }


def test_followup_uses_bounded_history_for_interpretation_and_retrieved_context() -> None:
    chain = FakeChain(response="The handbook says yes [1].")
    queries: list[str] = []

    def retrieve(query: str) -> list[RetrievedChunk]:
        queries.append(query)
        return [chunk()]

    service = ChatService(chain=chain, retrieve=retrieve)
    now = datetime(2026, 10, 9, tzinfo=timezone.utc)
    history = tuple(
        MessageRecord(id=index, speaker="user", content=f"Question {index}", created_at=now)
        for index in range(20)
    )
    answer = service.answer("What about that?", history)

    assert answer.citations[0].document_id == "policies_pdf"
    assert "Question 19" in queries[0]
    assert "Question 0" not in queries[0]
    assert "What about that?" in queries[0]
    assert chain.input is not None
    assert "Question 8" in chain.input["history"]
    assert "Question 7" not in chain.input["history"]
    assert chain.input["context"].startswith("[1] Source: policies.pdf")


def test_answer_abstains_without_calling_model_when_retrieval_is_empty() -> None:
    chain = FakeChain()
    service = ChatService(chain=chain, retrieve=lambda query: [])

    answer = service.answer("Unknown question")

    assert answer.text == ABSTENTION_MESSAGE
    assert answer.citations == ()
    assert chain.call_count == 0


def test_answer_accepts_model_abstention_for_insufficient_context() -> None:
    chain = FakeChain(response=ABSTENTION_MESSAGE)
    service = ChatService(chain=chain, retrieve=lambda query: [chunk()])

    answer = service.answer("Question not answered by this chunk")

    assert answer.text == ABSTENTION_MESSAGE
    assert answer.citations == ()
    assert chain.call_count == 1


def test_answer_wraps_model_failures() -> None:
    service = ChatService(
        chain=FakeChain(error=TimeoutError()),
        retrieve=lambda query: [chunk()],
    )

    with pytest.raises(AnswerGenerationError, match="Answer generation failed"):
        service.answer("Question")


def test_build_answer_rejects_unknown_citation() -> None:
    with pytest.raises(AnswerGenerationError, match="unknown citation"):
        build_answer("Unsupported claim [2].", [chunk()])


def test_build_answer_requires_a_citation() -> None:
    with pytest.raises(AnswerGenerationError, match="does not cite"):
        build_answer("Unsupported claim.", [chunk()])


def test_build_answer_deduplicates_repeated_markers_in_first_use_order() -> None:
    chunks = [chunk(1), chunk(2, page_number=4)]

    answer = build_answer("Second [2], first [1], and second again [2].", chunks)

    assert [citation.citation_id for citation in answer.citations] == [2, 1]


def test_format_context_uses_chunk_number_when_page_is_unavailable() -> None:
    assert format_context([chunk(page_number=None, chunk_index=2)]) == (
        "[1] Source: policies.pdf, chunk 3\nContext 1"
    )
