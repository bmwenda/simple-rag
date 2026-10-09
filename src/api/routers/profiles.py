"""Self-profile HTTP handlers."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from src.profile import (
    DuplicateEmailError,
    InvalidProfileError,
    Profile,
    ProfileNotFoundError,
)
from src.profile_service import ProfileService

from ..dependencies import current_profile, get_profile_service
from ..errors import ApiError
from ..schemas.profiles import ProfileResponse, ProfileUpdate

router = APIRouter(prefix="/users", tags=["profiles"])


@router.get("/me", response_model=ProfileResponse)
def get_my_profile(
    profile: Annotated[Profile, Depends(current_profile)],
) -> ProfileResponse:
    return ProfileResponse.from_profile(profile)


@router.patch("/me", response_model=ProfileResponse)
def update_my_profile(
    update: ProfileUpdate,
    profile: Annotated[Profile, Depends(current_profile)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> ProfileResponse:
    try:
        updated = service.update_profile(profile.id, update.model_dump(exclude_unset=True))
    except InvalidProfileError as error:
        raise ApiError(400, "invalid_request", str(error)) from None
    except DuplicateEmailError:
        raise ApiError(409, "email_conflict", "Email is already in use") from None
    except ProfileNotFoundError:
        raise ApiError(401, "unauthorized", "Invalid or missing credentials") from None
    return ProfileResponse.from_profile(updated)


@router.delete("/me", status_code=204)
def delete_my_profile(
    profile: Annotated[Profile, Depends(current_profile)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> Response:
    try:
        service.delete_profile(profile.id)
    except ProfileNotFoundError:
        raise ApiError(401, "unauthorized", "Invalid or missing credentials") from None
    return Response(status_code=204)
