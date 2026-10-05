from typing import Protocol

from src.chat import create_chat_service, format_source
from src.config import Settings
from src.domain import Answer, Citation, RAGError


class AnswerService(Protocol):
    def answer(self, query: str) -> Answer: ...


def chat(query: str, service: AnswerService) -> str:
    try:
        return format_answer(service.answer(query))
    except RAGError:
        return "Sorry, I couldn't answer that right now. Please try again."


def format_answer(answer: Answer) -> str:
    if not answer.citations:
        return answer.text

    grouped_citations: dict[tuple[str, int | None], list[Citation]] = {}
    for citation in answer.citations:
        key = (citation.document_id, citation.page_number)
        grouped_citations.setdefault(key, []).append(citation)

    sources = []
    for citations in grouped_citations.values():
        labels = ", ".join(str(citation.citation_id) for citation in citations)
        sources.append(f"[{labels}] {format_source(citations[0])}")

    return f"{answer.text}\n\nSources:\n" + "\n".join(sources)


def main() -> None:
    service = create_chat_service(Settings.from_env())
    print(
        "Hello new joiner! Welcome to Aetheris! Ask me any question regarding "
        "us, such as policies and other useful information.\nTo exit, type 'q', "
        "'quit', or 'exit'."
    )

    while True:
        user_input = input("> ")
        if user_input.strip().lower() in {"q", "quit", "exit"}:
            print("See you soon!!")
            break

        print(chat(user_input, service))


if __name__ == "__main__":
    main()
