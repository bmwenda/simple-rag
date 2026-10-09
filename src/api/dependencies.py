"""Authentication and service dependencies shared by API routers."""

import os
from hmac import compare_digest
from typing import Annotated, cast

from dotenv import load_dotenv
from fastapi import Depends, Header, Request

from src.chat_history_service import Answerer, ChatHistoryService, ChatRepository
from src.domain import Answer
from src.profile import Profile
from src.profile_service import ProfileRepository, ProfileService

from .errors import ApiError


def get_repository(request: Request) -> ProfileRepository:
    return cast(ProfileRepository, request.app.state.profile_repository)


def get_profile_service(
    repository: Annotated[ProfileRepository, Depends(get_repository)],
) -> ProfileService:
    return ProfileService(repository)


def get_chat_repository(request: Request) -> ChatRepository:
    with request.app.state.chat_repository_lock:
        repository = request.app.state.chat_repository
        if repository is None:
            repository = request.app.state.chat_repository_factory()
            request.app.state.chat_repository = repository
    return cast(ChatRepository, repository)


class LazyAnswerer:
    def answer(self, query: str) -> Answer:
        from src.chat import create_chat_service
        from src.config import Settings

        return create_chat_service(Settings.from_env()).answer(query)


def get_answerer() -> Answerer:
    return LazyAnswerer()


def get_chat_history_service(
    repository: Annotated[ChatRepository, Depends(get_chat_repository)],
    answerer: Annotated[Answerer, Depends(get_answerer)],
) -> ChatHistoryService:
    return ChatHistoryService(repository, answerer)


def verify_bearer(authorization: str | None = Header(default=None)) -> None:
    load_dotenv()
    expected = os.getenv("API_BEARER_TOKEN")
    if expected is None or len(expected) < 32:
        raise ApiError(503, "service_unavailable", "Profile service is unavailable")
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not supplied or not compare_digest(
        supplied, expected
    ):
        raise ApiError(401, "unauthorized", "Invalid or missing credentials")


def current_profile(
    _verified: Annotated[None, Depends(verify_bearer)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> Profile:
    profile = service.get_owner()
    if profile is None:
        raise ApiError(401, "unauthorized", "Invalid or missing credentials")
    return profile
