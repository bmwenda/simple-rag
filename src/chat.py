from collections.abc import Callable
from typing import Protocol

from langchain_core.prompts import ChatPromptTemplate

from .config import Settings
from .domain import AnswerGenerationError, ChatResponse
from .model import get_chat_model
from .retriever import retrieve_documents

SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer questions concisely and use only the "
    "company information as context.\n\nContext:\n{context}\nIf you don't have "
    "an answer from the context, politely guide the user to consult their "
    "manager, HR, or onboarding buddy for guidance."
)


class Message(Protocol):
    @property
    def text(self) -> str: ...


class Chain(Protocol):
    def invoke(self, input: dict[str, str]) -> Message: ...


class ChatService:
    def __init__(
        self,
        chain: Chain,
        retrieve: Callable[[str], str] = retrieve_documents,
    ) -> None:
        self._chain = chain
        self._retrieve = retrieve

    def answer(self, query: str) -> ChatResponse:
        context = self._retrieve(query)
        try:
            response = self._chain.invoke({"context": context, "query": query})
        except Exception as exc:
            raise AnswerGenerationError("Answer generation failed") from exc
        return ChatResponse(text=response.text)


def create_chat_service(settings: Settings) -> ChatService:
    prompt = ChatPromptTemplate.from_messages(
        [("system", SYSTEM_PROMPT), ("human", "{query}")]
    )
    chain = prompt | get_chat_model(settings)
    return ChatService(chain=chain)
