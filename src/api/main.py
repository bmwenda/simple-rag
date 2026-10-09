"""ASGI entry point and application lifecycle."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config import database_url_from_env
from src.profile_repository import SqlProfileRepository
from src.profile_service import ManagedProfileRepository

from .errors import register_error_handlers
from .routers.profiles import router as profile_router


def _default_repository() -> ManagedProfileRepository:
    return SqlProfileRepository(database_url_from_env())


def create_app(
    repository_factory: Callable[[], ManagedProfileRepository] = _default_repository,
) -> FastAPI:
    """Build the API without opening a database connection at import time."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        repository = repository_factory()
        application.state.profile_repository = repository
        try:
            yield
        finally:
            repository.close()
            del application.state.profile_repository

    application = FastAPI(
        lifespan=lifespan, openapi_url=None, docs_url=None, redoc_url=None
    )
    register_error_handlers(application)
    application.include_router(profile_router, prefix="/v1")
    return application


app = create_app()
