"""Application error hierarchy. Services raise these with user-facing messages (D-20)."""

from __future__ import annotations


class AppError(Exception):
    status_code = 400

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        field: str | None = None,
        errors: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.errors: dict[str, str] = dict(errors or {})
        if field and field not in self.errors:
            self.errors[field] = message


class ValidationFailed(AppError):
    status_code = 400


class Unauthorized(AppError):
    status_code = 401


class Forbidden(AppError):
    status_code = 403


class NotFound(AppError):
    status_code = 404


class Conflict(AppError):
    status_code = 409


class PayloadTooLarge(AppError):
    status_code = 413


class TooManyRequests(AppError):
    status_code = 429


class LoginRequired(Exception):
    """Raised by guards when no valid session exists. Rendered per request kind (D-45)."""

    def __init__(self, message: str = "Please login first") -> None:
        super().__init__(message)
        self.message = message


class AdminRequired(Exception):
    """Raised by guards when the user is not an admin (D-52)."""

    message = "Admin access required"


class CsrfFailed(Exception):
    def __init__(self, message: str = "Your session has expired. Please refresh the page and try again.") -> None:
        super().__init__(message)
        self.message = message


class BodyTooLarge(Exception):
    """Raised while reading a request body that exceeds the configured limit (FR-005)."""
