from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    AccessDeniedError,
    ApplicationError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)


def application_error_handler(
    request: Request,
    exc: ApplicationError,
) -> JSONResponse:
    status_code = 500

    if isinstance(exc, NotFoundError):
        status_code = 404
    elif isinstance(exc, AccessDeniedError):
        status_code = 403
    elif isinstance(exc, ConflictError):
        status_code = 409
    elif isinstance(exc, ValidationError):
        status_code = 422
    elif isinstance(exc, ServiceUnavailableError):
        status_code = 503

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
            }
        },
    )