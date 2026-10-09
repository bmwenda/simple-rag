"""Authenticated chat collection and lifecycle routes."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Response

from src.chat_history_service import ChatHistoryService
from src.profile import Profile

from ..dependencies import current_profile, get_chat_history_service
from ..schemas.chats import (
    ChatCreate,
    ChatCreateResponse,
    ChatListResponse,
    ChatResponse,
    ChatUpdate,
    FollowupResponse,
    MessageCreate,
    MessageListResponse,
    MessageResponse,
)

router = APIRouter(prefix="/chats", tags=["chats"])


@router.post("", status_code=201, response_model=ChatCreateResponse)
def create_chat(
    request: ChatCreate,
    profile: Annotated[Profile, Depends(current_profile)],
    service: Annotated[ChatHistoryService, Depends(get_chat_history_service)],
) -> ChatCreateResponse:
    chat, user_message, assistant_message = service.create_chat(profile.id, request.content)
    return ChatCreateResponse(
        chat=ChatResponse.from_record(chat),
        user_message=MessageResponse.from_record(user_message),
        assistant_message=MessageResponse.from_record(assistant_message),
    )


@router.get("", response_model=ChatListResponse)
def list_chats(
    profile: Annotated[Profile, Depends(current_profile)],
    service: Annotated[ChatHistoryService, Depends(get_chat_history_service)],
    status: Literal["active", "archived"] | None = None,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> ChatListResponse:
    return ChatListResponse.from_page(service.list_chats(profile.id, status, cursor, limit))


@router.get("/{chat_id}", response_model=ChatResponse)
def get_chat(
    chat_id: Annotated[int, Path(ge=1)],
    profile: Annotated[Profile, Depends(current_profile)],
    service: Annotated[ChatHistoryService, Depends(get_chat_history_service)],
) -> ChatResponse:
    return ChatResponse.from_record(service.get_chat(profile.id, chat_id))


@router.patch("/{chat_id}", response_model=ChatResponse)
def update_chat(
    chat_id: Annotated[int, Path(ge=1)],
    update: ChatUpdate,
    profile: Annotated[Profile, Depends(current_profile)],
    service: Annotated[ChatHistoryService, Depends(get_chat_history_service)],
) -> ChatResponse:
    changes = update.model_dump(exclude_unset=True)
    return ChatResponse.from_record(service.update_chat(profile.id, chat_id, changes))


@router.delete("/{chat_id}", status_code=204)
def delete_chat(
    chat_id: Annotated[int, Path(ge=1)],
    profile: Annotated[Profile, Depends(current_profile)],
    service: Annotated[ChatHistoryService, Depends(get_chat_history_service)],
) -> Response:
    service.delete_chat(profile.id, chat_id)
    return Response(status_code=204)


@router.get("/{chat_id}/messages", response_model=MessageListResponse)
def list_messages(
    chat_id: Annotated[int, Path(ge=1)],
    profile: Annotated[Profile, Depends(current_profile)],
    service: Annotated[ChatHistoryService, Depends(get_chat_history_service)],
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> MessageListResponse:
    return MessageListResponse.from_page(
        service.list_messages(profile.id, chat_id, cursor, limit)
    )


@router.post("/{chat_id}/messages", status_code=201, response_model=FollowupResponse)
def create_message(
    chat_id: Annotated[int, Path(ge=1)],
    request: MessageCreate,
    profile: Annotated[Profile, Depends(current_profile)],
    service: Annotated[ChatHistoryService, Depends(get_chat_history_service)],
) -> FollowupResponse:
    user_message, assistant_message = service.add_followup(
        profile.id, chat_id, request.content
    )
    return FollowupResponse(
        user_message=MessageResponse.from_record(user_message),
        assistant_message=MessageResponse.from_record(assistant_message),
    )
