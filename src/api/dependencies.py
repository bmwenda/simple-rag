"""Authentication and service dependencies shared by API routers."""

import os
from hmac import compare_digest
from typing import Annotated, cast

from dotenv import load_dotenv
from fastapi import Depends, Header, Request

from src.profile import Profile
from src.profile_service import ProfileRepository, ProfileService

from .errors import ApiError


def get_repository(request: Request) -> ProfileRepository:
    return cast(ProfileRepository, request.app.state.profile_repository)


def get_profile_service(
    repository: Annotated[ProfileRepository, Depends(get_repository)],
) -> ProfileService:
    return ProfileService(repository)


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
