from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        self.code, self.message, self.status = code, message, status
        super().__init__(code)


def error_response(request: Request, code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", "unavailable"),
                "details": {},
            }
        },
    )


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def application_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(request, exc.code, exc.message, exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(request, "invalid_request", "Request fields are invalid.", 422)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        if exc.status_code == 413:
            return error_response(
                request, "upload_too_large", "The upload exceeds the size limit.", 413
            )
        return error_response(
            request, "http_error", "The request could not be handled.", exc.status_code
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Any) -> JSONResponse:
        return error_response(
            request, "internal_error", "The operation could not be completed.", 500
        )
