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
    default_detail = "Add your Razorpay API keys to accept online payments."


class PaymentAccountInvalid(Conflict):
    default_code = "payment_account_invalid"
    default_detail = "Razorpay rejected these API keys. Check the key id and secret."
