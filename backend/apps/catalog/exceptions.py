"""Catalog API errors (docs/contracts/wave-3-commerce.md, "Error codes")."""

from rest_framework import exceptions

from common.exceptions import Conflict, FeatureNotAvailable


class EndpointNotImplemented(exceptions.APIException):
    """501 ``not_implemented``: the endpoint is in the contract but not built yet."""

    status_code = 501
    default_code = "not_implemented"
    default_detail = "This endpoint is not available yet."


class CatalogNotConnected(Conflict):
    default_code = "catalog_not_connected"
    default_detail = "Connect a Meta catalog to use native catalog shopping."


class CatalogPermissionsMissing(Conflict):
    """``details.reconnect_url`` is null: the UI tells the seller to reconnect WhatsApp."""

    default_code = "catalog_permissions_missing"
    default_detail = (
        "Your WhatsApp connection lacks catalog permissions. Reconnect WhatsApp to grant them."
    )

    def __init__(self, detail=None, code=None) -> None:
        message = str(detail) if detail is not None else str(self.default_detail)
        super().__init__(message, code)
        # common.exceptions builds the envelope from default_detail (message) and a dict detail.
        self.default_detail = message
        self.detail = {"reconnect_url": None}


class OutOfStock(Conflict):
    """409 ``out_of_stock`` with ``details.items``: ``[{sku, name, requested, available}]``."""

    default_code = "out_of_stock"
    default_detail = "Some items are out of stock."

    def __init__(self, items=(), detail=None, code=None) -> None:
        self.items = [dict(item) for item in items]
        message = str(detail) if detail is not None else str(self.default_detail)
        super().__init__(message, code)
        self.default_detail = message
        self.detail = {"items": self.items}


class CommerceNotEnabled(FeatureNotAvailable):
    """409 ``commerce_not_enabled``: the plan lacks the ``commerce`` feature (wave-3 error table).

    A ``FeatureNotAvailable`` subclass, so generic plan-error handling still catches it.
    """

    default_code = "commerce_not_enabled"
    default_detail = (
        "Your plan does not include the WhatsApp store. Upgrade your plan to manage the catalog."
    )


class WhatsAppNotConnected(Conflict):
    default_code = "whatsapp_not_connected"
    default_detail = (
        "This WhatsApp Business Account is not connected. Reconnect WhatsApp to manage catalogs."
    )
