"""Graph API errors, mapped from Meta error codes.

``retryable`` tells Celery tasks whether to retry with backoff. Codes follow Meta's Cloud API
error reference; unknown codes fall back to TransientError for HTTP 5xx and GraphAPIError otherwise.
"""

from collections.abc import Mapping
from typing import Any


class GraphAPIError(Exception):
    retryable: bool = False

    def __init__(
        self,
        message: str = "",
        *,
        http_status: int | None = None,
        code: int | None = None,
        subcode: int | None = None,
        error_type: str | None = None,
        fbtrace_id: str | None = None,
        details: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.http_status = http_status
        self.code = code
        self.subcode = subcode
        self.error_type = error_type
        self.fbtrace_id = fbtrace_id
        self.details = details
        self.retry_after = retry_after

    def __str__(self) -> str:
        return f"{self.message} (code={self.code}, subcode={self.subcode}, http={self.http_status})"


class NetworkError(GraphAPIError):
    """Timeout or connection failure before Meta answered."""

    retryable = True


class TransientError(GraphAPIError):
    retryable = True


class RateLimitedError(GraphAPIError):
    retryable = True


class TokenInvalidError(GraphAPIError):
    """Token expired, revoked or missing permissions: the customer must reconnect."""


class GraphPermissionError(GraphAPIError):
    pass


class InvalidParameterError(GraphAPIError):
    pass


class OutsideWindowError(GraphAPIError):
    """More than 24 hours since the customer's last message: only templates may be sent."""


class RecipientOptedOutError(GraphAPIError):
    """131050: the user stopped marketing messages from this business."""


class RecipientUnavailableError(GraphAPIError):
    """Undeliverable (not on WhatsApp, old app) or held back by Meta for this user."""


class TemplateError(GraphAPIError):
    pass


class PhoneRegistrationError(GraphAPIError):
    pass


class AccountRestrictedError(GraphAPIError):
    """Account locked, policy-blocked or spam-limited. Do not retry automatically."""


class PaymentRequiredError(GraphAPIError):
    pass


_CODE_MAP: dict[int, type[GraphAPIError]] = {
    1: TransientError,
    2: TransientError,
    131000: TransientError,
    131016: TransientError,
    133004: TransientError,
    4: RateLimitedError,
    17: RateLimitedError,
    32: RateLimitedError,
    613: RateLimitedError,
    80007: RateLimitedError,
    130429: RateLimitedError,
    131056: RateLimitedError,
    0: TokenInvalidError,
    102: TokenInvalidError,
    190: TokenInvalidError,
    3: GraphPermissionError,
    10: GraphPermissionError,
    100: InvalidParameterError,
    131008: InvalidParameterError,
    131009: InvalidParameterError,
    131021: InvalidParameterError,
    131051: InvalidParameterError,
    131052: InvalidParameterError,
    131053: InvalidParameterError,
    135000: InvalidParameterError,
    131047: OutsideWindowError,
    131050: RecipientOptedOutError,
    131026: RecipientUnavailableError,
    131049: RecipientUnavailableError,
    131031: AccountRestrictedError,
    131048: AccountRestrictedError,
    368: AccountRestrictedError,
    130497: AccountRestrictedError,
    131042: PaymentRequiredError,
}


def _class_for_code(code: int | None, http_status: int) -> type[GraphAPIError]:
    if code is not None:
        if code in _CODE_MAP:
            return _CODE_MAP[code]
        if 200 <= code <= 299:
            return GraphPermissionError
        if 132000 <= code <= 132999:
            return TemplateError
        if 133000 <= code <= 133999:
            return PhoneRegistrationError
    if http_status == 429:
        return RateLimitedError
    if http_status >= 500:
        return TransientError
    return GraphAPIError


def error_from_response(
    http_status: int, body: Any, headers: Mapping[str, str] | None = None
) -> GraphAPIError:
    """Build the right GraphAPIError subclass from an error response."""
    retry_after = None
    if headers:
        raw_retry = headers.get("Retry-After") or headers.get("retry-after")
        if raw_retry and str(raw_retry).isdigit():
            retry_after = int(raw_retry)

    error = body.get("error") if isinstance(body, Mapping) else None
    if not isinstance(error, Mapping):
        error_class = _class_for_code(None, http_status)
        return error_class(
            f"Graph API returned HTTP {http_status}",
            http_status=http_status,
            retry_after=retry_after,
        )

    code = error.get("code")
    code = int(code) if isinstance(code, int | str) and str(code).isdigit() else None
    error_data = error.get("error_data")
    details = error_data.get("details") if isinstance(error_data, Mapping) else None
    return _class_for_code(code, http_status)(
        error.get("message", ""),
        http_status=http_status,
        code=code,
        subcode=error.get("error_subcode"),
        error_type=error.get("type"),
        fbtrace_id=error.get("fbtrace_id"),
        details=details,
        retry_after=retry_after,
    )
