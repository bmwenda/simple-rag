"""Application use cases for the chat collection and lifecycle."""

from typing import Protocol

from .chat_history import (
    ChatPage,
    ChatRecord,
    MessagePage,
    MessageRecord,
    PendingChat,
    PendingMessage,
    normalize_content,
    normalize_update,
    title_from_question,
)
from .domain import Answer, Citation

MAX_HISTORY_MESSAGES = 12


class ChatRepository(Protocol):
    def create_chat(self, user_id: int, title: str, content: str) -> tuple[ChatRecord, MessageRecord]: ...

    def begin_chat(self, user_id: int, title: str, content: str) -> PendingChat: ...

    def add_assistant_message(
        self, user_id: int, chat_id: int, content: str, citations: tuple[Citation, ...]
    ) -> MessageRecord: ...

    def list_chats(
        self, user_id: int, status: str | None, cursor: str | None, limit: int
    ) -> ChatPage: ...

    def get_chat(self, user_id: int, chat_id: int) -> ChatRecord: ...

    def update_chat(self, user_id: int, chat_id: int, changes: dict[str, str]) -> ChatRecord: ...

    def delete_chat(self, user_id: int, chat_id: int) -> None: ...

    def list_messages(
        self, user_id: int, chat_id: int, cursor: str | None, limit: int
    ) -> MessagePage: ...

    def begin_followup(
        self, user_id: int, chat_id: int, content: str, history_limit: int
    ) -> PendingMessage: ...

    def complete_followup(
        self,
        user_id: int,
        chat_id: int,
        token: str,
        content: str,
        citations: tuple[Citation, ...],
    ) -> MessageRecord: ...

    def release_followup(self, chat_id: int, token: str) -> None: ...


class ManagedChatRepository(ChatRepository, Protocol):
    def close(self) -> None: ...


class Answerer(Protocol):
    def answer(
        self, query: str, history: tuple[MessageRecord, ...] = ()
    ) -> Answer: ...


class ChatHistoryService:
    def __init__(self, repository: ChatRepository, answerer: Answerer) -> None:
        self._repository = repository
        self._answerer = answerer

    def create_chat(self, user_id: int, content: str) -> tuple[ChatRecord, MessageRecord, MessageRecord]:
        question = normalize_content(content)
        pending = self._repository.begin_chat(
            user_id, title_from_question(question), question
        )
        try:
            answer = self._answerer.answer(question)
            assistant_message = self._repository.complete_followup(
                user_id, pending.chat.id, pending.token, answer.text, answer.citations
            )
        except Exception:
            self._repository.release_followup(pending.chat.id, pending.token)
            raise
        return (
            self._repository.get_chat(user_id, pending.chat.id),
            pending.user_message,
            assistant_message,
        )

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

    def list_messages(
        self, user_id: int, chat_id: int, cursor: str | None, limit: int
    ) -> MessagePage:
        return self._repository.list_messages(user_id, chat_id, cursor, limit)

    def add_followup(
        self, user_id: int, chat_id: int, content: str
    ) -> tuple[MessageRecord, MessageRecord]:
        question = normalize_content(content)
        pending = self._repository.begin_followup(
            user_id, chat_id, question, MAX_HISTORY_MESSAGES
        )
        try:
            answer = self._answerer.answer(question, pending.history)
            assistant = self._repository.complete_followup(
                user_id, chat_id, pending.token, answer.text, answer.citations
            )
        except Exception:
            self._repository.release_followup(chat_id, pending.token)
            raise
        return pending.user_message, assistant
