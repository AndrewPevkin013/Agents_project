class ApplicationError(Exception):
    """Base class for expected application-level errors."""

    code = "APPLICATION_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(ApplicationError):
    code = "NOT_FOUND"


class AccessDeniedError(ApplicationError):
    code = "ACCESS_DENIED"


class ConflictError(ApplicationError):
    code = "CONFLICT"


class ValidationError(ApplicationError):
    code = "VALIDATION_ERROR"


class ServiceUnavailableError(ApplicationError):
    code = "SERVICE_UNAVAILABLE"