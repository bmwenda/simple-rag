import main
from src.domain import ChatResponse, RAGError


class SuccessfulService:
    def answer(self, query: str) -> ChatResponse:
        return ChatResponse(text="A safe answer")


class FailingService:
    def answer(self, query: str) -> ChatResponse:
        raise RAGError("internal detail")


def test_chat_returns_service_answer() -> None:
    assert main.chat("Question", SuccessfulService()) == "A safe answer"


def test_chat_does_not_expose_internal_error() -> None:
    response = main.chat("Question", FailingService())

    assert response == "Sorry, I couldn't answer that right now. Please try again."
    assert "internal detail" not in response
