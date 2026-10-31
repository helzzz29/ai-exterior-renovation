"""Plain-language API errors rendered as `ApiError` bodies."""

from fastapi import Request
from fastapi.responses import JSONResponse

from app.domain.api import ApiError


class ApiException(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def not_found(what: str = "item") -> ApiException:
    return ApiException(404, "not_found", f"We couldn't find that {what}.")


def conflict(code: str, message: str) -> ApiException:
    return ApiException(409, code, message)


def invalid(code: str, message: str) -> ApiException:
    return ApiException(422, code, message)


async def api_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiException)
    body = ApiError(code=exc.code, message=exc.message)
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())
