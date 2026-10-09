"""Public chat collection request and response models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from src.chat_history import ChatPage, ChatRecord, ChatSummary, MessageRecord
from src.domain import Citation


class ChatCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    content: str = Field(max_length=10000)


class ChatUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: str | None = Field(default=None, max_length=120)
    status: Literal["active", "archived"] | None = None

    @model_validator(mode="after")
    def require_change(self) -> "ChatUpdate":
        if not self.model_fields_set or any(
            getattr(self, field) is None for field in self.model_fields_set
        ):
            raise ValueError("Provide a title or status")
        return self


class ChatResponse(BaseModel):
    id: int
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None

    @field_serializer("created_at", "updated_at", "archived_at")
    def serialize_timestamp(self, value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    @classmethod
    def from_record(cls, chat: ChatRecord) -> "ChatResponse":
        return cls(**vars(chat))


class ChatSummaryResponse(ChatResponse):
    latest_activity_at: datetime

    @field_serializer("latest_activity_at")
    def serialize_activity(self, value: datetime) -> str:
        return value.isoformat()

    @classmethod
    def from_summary(cls, summary: ChatSummary) -> "ChatSummaryResponse":
        return cls(**vars(summary.chat), latest_activity_at=summary.latest_activity_at)


class ChatListResponse(BaseModel):
    items: list[ChatSummaryResponse]
    next_cursor: str | None

    @classmethod
    def from_page(cls, page: ChatPage) -> "ChatListResponse":
        return cls(
            items=[ChatSummaryResponse.from_summary(item) for item in page.items],
            next_cursor=page.next_cursor,
        )


class CitationResponse(BaseModel):
    citation_number: int
    document_id: str
    index_version: int
    chunk_index: int
    display_name: str
    page_number: int | None
    excerpt: str

    @classmethod
    def from_citation(cls, citation: Citation) -> "CitationResponse":
        return cls(
            citation_number=citation.citation_id,
            document_id=citation.document_id,
            index_version=citation.index_version,
            chunk_index=citation.chunk_index,
            display_name=citation.display_name,
            page_number=citation.page_number,
            excerpt=citation.excerpt,
        )


class MessageResponse(BaseModel):
    id: int
    speaker: str
    content: str
    created_at: datetime
    citations: list[CitationResponse]

    @field_serializer("created_at")
    def serialize_timestamp(self, value: datetime) -> str:
        return value.isoformat()

    @classmethod
    def from_record(cls, message: MessageRecord) -> "MessageResponse":
        return cls(
            id=message.id,
            speaker=message.speaker,
            content=message.content,
            created_at=message.created_at,
            citations=[CitationResponse.from_citation(item) for item in message.citations],
        )


class ChatCreateResponse(BaseModel):
    chat: ChatResponse
    user_message: MessageResponse
    assistant_message: MessageResponse
