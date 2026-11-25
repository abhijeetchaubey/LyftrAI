"""
Exception classes and handlers for the application.
"""
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder


class AllProvidersUnavailableException(HTTPException):
    """Raised when all configured LLM API keys fail."""
    def __init__(self, detail: str = "all providers unavailable"):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail
        )


class SessionNotFoundException(HTTPException):
    """Raised when a requested session is not found in the database."""
    def __init__(self, detail: str = "session not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail
        )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Standardized handler for HTTPExceptions ensuring clean JSON error response."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Standardized handler for RequestValidationError returning 422 with a detail field.
    Never exposes stack traces or internal implementation details.
    """
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors())}
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler ensuring internal server errors return a clean JSON object
    and never expose stack traces or HTML error pages.
    """
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"}
    )
