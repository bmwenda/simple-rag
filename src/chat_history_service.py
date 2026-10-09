"""Application use cases for the chat collection and lifecycle."""

from typing import Protocol

from .chat_history import (
    ChatPage,
    ChatRecord,
    MessageRecord,
    normalize_content,
    normalize_update,
    title_from_question,
)
from .domain import Answer, Citation


class ChatRepository(Protocol):
    def create_chat(self, user_id: int, title: str, content: str) -> tuple[ChatRecord, MessageRecord]: ...

    def add_assistant_message(
        self, user_id: int, chat_id: int, content: str, citations: tuple[Citation, ...]
    ) -> MessageRecord: ...

    def list_chats(
        self, user_id: int, status: str | None, cursor: str | None, limit: int
    ) -> ChatPage: ...

    def get_chat(self, user_id: int, chat_id: int) -> ChatRecord: ...

    def update_chat(self, user_id: int, chat_id: int, changes: dict[str, str]) -> ChatRecord: ...

    def delete_chat(self, user_id: int, chat_id: int) -> None: ...


class ManagedChatRepository(ChatRepository, Protocol):
    def close(self) -> None: ...


class Answerer(Protocol):
    def answer(self, query: str) -> Answer: ...


class ChatHistoryService:
    def __init__(self, repository: ChatRepository, answerer: Answerer) -> None:
        self._repository = repository
        self._answerer = answerer

    def create_chat(self, user_id: int, content: str) -> tuple[ChatRecord, MessageRecord, MessageRecord]:
        question = normalize_content(content)
        chat, user_message = self._repository.create_chat(
            user_id, title_from_question(question), question
        )
        answer = self._answerer.answer(question)
        assistant_message = self._repository.add_assistant_message(
            user_id, chat.id, answer.text, answer.citations
        )
        return self._repository.get_chat(user_id, chat.id), user_message, assistant_message

    def list_chats(
        self, user_id: int, status: str | None, cursor: str | None, limit: int
    ) -> ChatPage:
        return self._repository.list_chats(user_id, status, cursor, limit)

    def get_chat(self, user_id: int, chat_id: int) -> ChatRecord:
        return self._repository.get_chat(user_id, chat_id)

    def update_chat(self, user_id: int, chat_id: int, changes: dict[str, str]) -> ChatRecord:
        return self._repository.update_chat(user_id, chat_id, normalize_update(changes))

    def delete_chat(self, user_id: int, chat_id: int) -> None:
        self._repository.delete_chat(user_id, chat_id)
