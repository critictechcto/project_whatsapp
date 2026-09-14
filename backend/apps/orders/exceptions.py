"""Orders and store API errors (docs/contracts/wave-3-commerce.md, "Error codes")."""

from rest_framework import exceptions

from common.exceptions import Conflict


class EndpointNotImplemented(exceptions.APIException):
    """501 ``not_implemented``: the endpoint is in the contract but not built yet."""

    status_code = 501
    default_code = "not_implemented"
    default_detail = "This endpoint is not available yet."


class CommerceNotEnabled(Conflict):
    """The store is disabled or the plan lacks ``commerce``. Pass a message naming what's
    missing."""

    default_code = "commerce_not_enabled"
    default_detail = "Selling on WhatsApp is not enabled for this workspace."


class CatalogNotConnected(Conflict):
    """Same code as ``apps.catalog.exceptions.CatalogNotConnected`` (not an allowed import)."""

    default_code = "catalog_not_connected"
    default_detail = "Connect a Meta catalog to use native catalog shopping."


class CheckoutRejected(ValueError):
    """``start_checkout`` could not create an order; the buyer was already told why.

    ``reason`` is ``empty_cart`` (nothing in the cart can be ordered) or ``below_minimum``
    (the subtotal is under ``StoreSettings.min_order_paise``).
    """

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason


class InvalidOrderTransition(Conflict):
    """409 ``invalid_order_transition``; ``details`` is ``{from_status, to_status, allowed}``."""

    default_code = "invalid_order_transition"
    default_detail = "This order can't move to that status."

    def __init__(
        self,
        from_status: str,
        to_status: str,
        allowed=(),
        detail=None,
        code=None,
    ) -> None:
        self.from_status, self.to_status, self.allowed = from_status, to_status, list(allowed)
        message = (
            str(detail)
            if detail is not None
            else f"An order that is {from_status} can't be moved to {to_status}."
        )
        super().__init__(message, code)
        # common.exceptions builds the envelope from default_detail (message) and a dict detail.
        self.default_detail = message
        self.detail = {
            "from_status": from_status,
            "to_status": to_status,
            "allowed": self.allowed,
        }
