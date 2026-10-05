import main
from src.domain import Answer, Citation, RAGError


def citation(
    citation_id: int,
    *,
    page_number: int | None = 3,
    chunk_index: int = 0,
) -> Citation:
    return Citation(
        citation_id=citation_id,
        document_id="policies_pdf",
        display_name="policies.pdf",
        page_number=page_number,
        chunk_index=chunk_index,
        excerpt="Supporting text",
    )


class SuccessfulService:
    def answer(self, query: str) -> Answer:
        return Answer(
            text="A supported answer [1].",
            citations=(citation(1),),
        )


class FailingService:
    def answer(self, query: str) -> Answer:
        raise RAGError("internal detail")


def test_chat_renders_answer_and_sources() -> None:
    assert main.chat("Question", SuccessfulService()) == (
        "A supported answer [1].\n\nSources:\n[1] policies.pdf, page 3"
    )


def test_format_answer_deduplicates_chunks_from_the_same_page() -> None:
    answer = Answer(
        text="A supported answer [1] [2].",
        citations=(citation(1), citation(2, chunk_index=1)),
    )

    assert main.format_answer(answer) == (
        "A supported answer [1] [2].\n\nSources:\n[1, 2] policies.pdf, page 3"
    )


def test_format_answer_renders_text_chunk_source() -> None:
    answer = Answer(
        text="A supported answer [1].",
        citations=(citation(1, page_number=None, chunk_index=2),),
    )

    assert main.format_answer(answer).endswith("[1] policies.pdf, chunk 3")


def test_format_answer_omits_sources_for_abstention() -> None:
    answer = Answer(text="No answer.", citations=())

    assert main.format_answer(answer) == "No answer."


def test_chat_does_not_expose_internal_error() -> None:
    response = main.chat("Question", FailingService())

    assert response == "Sorry, I couldn't answer that right now. Please try again."
    assert "internal detail" not in response
