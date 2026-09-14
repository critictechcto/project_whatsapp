"""Payments API errors (docs/contracts/wave-3-commerce.md, "Error codes")."""

from rest_framework import exceptions

from common.exceptions import Conflict


class EndpointNotImplemented(exceptions.APIException):
    """501 ``not_implemented``: the endpoint is in the contract but not built yet."""

    status_code = 501
    default_code = "not_implemented"
    default_detail = "This endpoint is not available yet."


class PaymentAccountMissing(Conflict):
    default_code = "payment_account_missing"
    default_detail = "Connect your payment gateway to accept online payments."


class PaymentAccountInvalid(Conflict):
    default_code = "payment_account_invalid"
    default_detail = "Your payment gateway rejected these API keys. Check the key id and secret."


class PaymentProviderError(Exception):
    """A gateway call failed. ``retryable`` is true for timeouts, rate limits and 5xx responses.

    The message never contains credentials.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable
