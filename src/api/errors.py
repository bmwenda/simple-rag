"""Shared JSON error format for HTTP routes."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.chat_history import ArchivedChatError, ChatNotFoundError, InvalidChatError


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ChatNotFoundError)
    async def chat_not_found(_request: Request, _error: ChatNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "Chat not found"}},
        )

    @app.exception_handler(ArchivedChatError)
    async def archived_chat(_request: Request, _error: ArchivedChatError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "chat_archived", "message": "Chat is archived"}},
        )

    @app.exception_handler(InvalidChatError)
    async def invalid_chat(_request: Request, _error: InvalidChatError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "invalid_request", "message": "Invalid request"}},
        )

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
            content={
                "error": {"code": "invalid_request", "message": "Invalid request"}
            },
        )

    @app.exception_handler(Exception)
    async def service_error_handler(
        _request: Request, _error: Exception
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "service_unavailable",
                    "message": "Profile service is unavailable",
                }
            },
        )
