class AppError(Exception):
    """A failure the client caused and can fix. Mapped to a JSON error response in main.py."""

    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str, *, code: str | None = None, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field
        if code:
            self.code = code


class Unauthorized(AppError):
    status_code = 401
    code = "UNAUTHORIZED"


class Forbidden(AppError):
    status_code = 403
    code = "FORBIDDEN"


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"


class Conflict(AppError):
    status_code = 409
    code = "CONFLICT"


class InvalidInput(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"
