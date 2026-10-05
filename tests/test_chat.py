from dataclasses import dataclass

import pytest

from src.chat import ChatService
from src.domain import AnswerGenerationError


@dataclass
class FakeMessage:
    text: str


class FakeChain:
    def __init__(self, response: str = "An answer", error: Exception | None = None):
        self.response = response
        self.error = error
        self.input: dict[str, str] | None = None

    def invoke(self, input: dict[str, str]) -> FakeMessage:
        self.input = input
        if self.error:
            raise self.error
        return FakeMessage(self.response)


def test_answer_passes_retrieved_context_to_chain() -> None:
    chain = FakeChain(response="Use the handbook.")
    service = ChatService(chain=chain, retrieve=lambda query: f"Context for {query}")

    response = service.answer("Where is the policy?")

    assert response.text == "Use the handbook."
    assert chain.input == {
        "context": "Context for Where is the policy?",
        "query": "Where is the policy?",
    }


def test_answer_wraps_model_failures() -> None:
    service = ChatService(
        chain=FakeChain(error=TimeoutError()),
        retrieve=lambda query: "Context",
    )

    with pytest.raises(AnswerGenerationError, match="Answer generation failed"):
        service.answer("Question")
