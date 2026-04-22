"""Custom exceptions for the Subconscious SDK."""

from typing import Any, Literal

ErrorCode = Literal[
    'invalid_request',
    'authentication_failed',
    'permission_denied',
    'not_found',
    'rate_limited',
    'internal_error',
    'service_unavailable',
    'timeout',
]


class SubconsciousError(Exception):
    """Base exception for Subconscious API errors."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status: int,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = details

    def __str__(self) -> str:
        return f'{self.code}: {self.args[0]}'


class AuthenticationError(SubconsciousError):
    """Raised when API key is invalid or missing."""

    def __init__(self, message: str = 'Invalid API key'):
        super().__init__('authentication_failed', message, 401)


class RateLimitError(SubconsciousError):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str = 'Rate limit exceeded'):
        super().__init__('rate_limited', message, 429)


class NotFoundError(SubconsciousError):
    """Raised when a resource is not found."""

    def __init__(self, message: str = 'Resource not found'):
        super().__init__('not_found', message, 404)


class ValidationError(SubconsciousError):
    """Raised when request validation fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__('invalid_request', message, 400, details)


def _status_to_code(status: int) -> ErrorCode:
    """Map HTTP status codes to error codes."""
    mapping: dict[int, ErrorCode] = {
        400: 'invalid_request',
        401: 'authentication_failed',
        403: 'permission_denied',
        404: 'not_found',
        429: 'rate_limited',
        503: 'service_unavailable',
        504: 'timeout',
    }
    return mapping.get(status, 'internal_error')


def raise_for_status(response) -> None:
    """Raise appropriate exception based on response status.

    Extracts error info from three wire shapes the server may return:

    - Canonical SDK shape: ``{"error": {"code", "message", "details"}}``
    - Express default:     ``{"error": "Internal server error"}``
    - Plain text/unknown:  falls back to ``response.text``

    Enriches the message with method + URL so users get enough context
    to correlate with server logs (especially for 5xx responses where
    the body is generic).
    """
    if response.status_code < 400:
        return

    try:
        body = response.json()
    except Exception:
        body = None

    error_field = body.get('error') if isinstance(body, dict) else None
    if isinstance(error_field, dict):
        code = error_field.get('code', _status_to_code(response.status_code))
        message = error_field.get('message') or str(error_field)
        details = error_field.get('details')
    elif isinstance(error_field, str):
        code = _status_to_code(response.status_code)
        message = error_field
        details = None
    else:
        code = _status_to_code(response.status_code)
        message = response.text or f'HTTP {response.status_code}'
        details = None

    # Context suffix: "[GET /v1/runs/<id>]" and a request id when the
    # server surfaces one. Skipped quietly if the request object isn't
    # reachable (e.g., requests.Response without a bound PreparedRequest).
    request = getattr(response, 'request', None)
    method = getattr(request, 'method', None)
    url = getattr(request, 'url', None)
    request_id = response.headers.get('x-request-id') if response.headers else None
    suffix_parts = []
    if method and url:
        suffix_parts.append(f'{method} {url}')
    if request_id:
        suffix_parts.append(f'request_id={request_id}')
    if suffix_parts:
        message = f'{message} [{" ".join(suffix_parts)}]'

    if code == 'authentication_failed':
        raise AuthenticationError(message)
    elif code == 'rate_limited':
        raise RateLimitError(message)
    elif code == 'not_found':
        raise NotFoundError(message)
    elif code == 'invalid_request':
        raise ValidationError(message, details)
    else:
        raise SubconsciousError(code, message, response.status_code, details)
