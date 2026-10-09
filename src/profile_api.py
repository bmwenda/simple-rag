"""Authenticated v1 self-profile HTTP endpoints."""

import os
from functools import lru_cache
from hmac import compare_digest
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .config import database_url_from_env
from .profile import (
    DuplicateEmailError,
    InvalidProfileError,
    Profile,
    ProfileNotFoundError,
    normalize_changes,
)
from .profile_repository import SqlProfileRepository


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    email: str | None = Field(default=None, max_length=254)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


@lru_cache(maxsize=1)
def get_repository() -> SqlProfileRepository:
    return SqlProfileRepository(database_url_from_env())


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
    repository: Annotated[SqlProfileRepository, Depends(get_repository)],
) -> Profile:
    profile = repository.get_owner()
    if profile is None:
        raise ApiError(401, "unauthorized", "Invalid or missing credentials")
    return profile


app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)


@app.exception_handler(ApiError)
async def api_error_handler(_request: Request, error: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"error": {"code": error.code, "message": error.message}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _request: Request, _error: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "invalid_request", "message": "Invalid request"}},
    )


@app.exception_handler(Exception)
async def service_error_handler(_request: Request, _error: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "service_unavailable",
                "message": "Profile service is unavailable",
            }
        },
    )


@app.get("/v1/users/me")
def get_my_profile(
    profile: Annotated[Profile, Depends(current_profile)],
) -> dict[str, object]:
    return jsonable_encoder(profile)


@app.patch("/v1/users/me")
def update_my_profile(
    update: ProfileUpdate,
    profile: Annotated[Profile, Depends(current_profile)],
    repository: Annotated[SqlProfileRepository, Depends(get_repository)],
) -> dict[str, object]:
    try:
        changes = normalize_changes(update.model_dump(exclude_unset=True))
        updated = repository.update_profile(profile.id, changes)
    except InvalidProfileError as error:
        raise ApiError(400, "invalid_request", str(error)) from None
    except DuplicateEmailError:
        raise ApiError(409, "email_conflict", "Email is already in use") from None
    except ProfileNotFoundError:
        raise ApiError(401, "unauthorized", "Invalid or missing credentials") from None
    return jsonable_encoder(updated)


@app.delete("/v1/users/me", status_code=204)
def delete_my_profile(
    profile: Annotated[Profile, Depends(current_profile)],
    repository: Annotated[SqlProfileRepository, Depends(get_repository)],
) -> Response:
    try:
        repository.delete_profile(profile.id)
    except ProfileNotFoundError:
        raise ApiError(401, "unauthorized", "Invalid or missing credentials") from None
    return Response(status_code=204)
