"""Seller alerts API errors (docs/contracts/wave-3-commerce.md, "Error codes")."""

from rest_framework import exceptions

from common.exceptions import Conflict


class EndpointNotImplemented(exceptions.APIException):
    """501 ``not_implemented``: the endpoint is in the contract but not built yet."""

    status_code = 501
    default_code = "not_implemented"
    default_detail = "This endpoint is not available yet."


class AlertNumberUnverified(Conflict):
    default_code = "alert_number_unverified"
    default_detail = "Verify an alert number first."


class PlatformAlertsUnavailable(Conflict):
    default_code = "platform_alerts_unavailable"
    default_detail = "WhatsApp order alerts are not available right now."


class AlertRecipientLimit(Conflict):
    default_code = "alert_recipient_limit"
    default_detail = "A workspace can have at most 3 alert numbers."


class VerificationRecentlySent(Conflict):
    default_code = "verification_recently_sent"
    default_detail = "A verification message was sent in the last 5 minutes. Try again later."
