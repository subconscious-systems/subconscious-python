"""Custom exceptions for the Subconscious SDK."""

from typing import Any, Dict, Literal, Optional

ErrorCode = Literal[
    "invalid_request",
    "authentication_failed",
    "permission_denied",
    "not_found",
    "rate_limited",
    "internal_error",
    "service_unavailable",
    "timeout",
]


class SubconsciousError(Exception):
    """Base exception for Subconscious API errors."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status: int,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = details

    def __str__(self) -> str:
        return f"{self.code}: {self.args[0]}"


class AuthenticationError(SubconsciousError):
    """Raised when API key is invalid or missing."""

    def __init__(self, message: str = "Invalid API key"):
        super().__init__("authentication_failed", message, 401)


class RateLimitError(SubconsciousError):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__("rate_limited", message, 429)


class NotFoundError(SubconsciousError):
    """Raised when a resource is not found."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__("not_found", message, 404)


class ValidationError(SubconsciousError):
    """Raised when request validation fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("invalid_request", message, 400, details)


def _status_to_code(status: int) -> ErrorCode:
    """Map HTTP status codes to error codes."""
    mapping: Dict[int, ErrorCode] = {
        400: "invalid_request",
        401: "authentication_failed",
        403: "permission_denied",
        404: "not_found",
        429: "rate_limited",
        503: "service_unavailable",
        504: "timeout",
    }
    return mapping.get(status, "internal_error")


def raise_for_status(response) -> None:
    """Raise appropriate exception based on response status."""
    if response.status_code >= 400:
        try:
            body = response.json()
            error = body.get("error", {})
            code = error.get("code", _status_to_code(response.status_code))
            message = error.get("message", response.text or f"HTTP {response.status_code}")
            details = error.get("details")
        except Exception:
            code = _status_to_code(response.status_code)
            message = response.text or f"HTTP {response.status_code}"
            details = None

        if code == "authentication_failed":
            raise AuthenticationError(message)
        elif code == "rate_limited":
            raise RateLimitError(message)
        elif code == "not_found":
            raise NotFoundError(message)
        elif code == "invalid_request":
            raise ValidationError(message, details)
        else:
            raise SubconsciousError(code, message, response.status_code, details)

