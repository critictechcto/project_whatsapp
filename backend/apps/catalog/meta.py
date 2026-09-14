"""Connecting Meta catalogs and per-number commerce settings.

Every Graph call uses the WABA's own token through ``apps.whatsapp.client.get_client``. Tokens
are never logged or returned.
"""

import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.whatsapp import services as whatsapp_services
from apps.whatsapp.client import GraphAPIError, get_client
from apps.whatsapp.client.errors import GraphPermissionError, TokenInvalidError
from apps.whatsapp.models import PhoneNumber, WhatsAppBusinessAccount
from common.exceptions import UpstreamUnavailable

from . import sync
from .exceptions import CatalogPermissionsMissing, WhatsAppNotConnected
from .models import CatalogSyncBatch, MetaCatalog, MetaCatalogPhoneSetting, Product

logger = logging.getLogger(__name__)


def workspace_waba(workspace, waba_pk, *, field: str = "waba_id") -> WhatsAppBusinessAccount:
    waba = WhatsAppBusinessAccount.objects.filter(workspace=workspace, pk=waba_pk).first()
    if waba is None:
        raise serializers.ValidationError({field: ["WhatsApp Business Account not found."]})
    return waba


def ensure_connected(waba: WhatsAppBusinessAccount) -> None:
    if not sync.waba_can_sync(waba):
        raise WhatsAppNotConnected()


def meta_error(exc: GraphAPIError) -> Exception:
    """An API error for a failed Graph call, carrying nothing but Meta's message."""
    if isinstance(exc, GraphPermissionError | TokenInvalidError):
        return CatalogPermissionsMissing()
    if exc.retryable:
        return UpstreamUnavailable()
    return whatsapp_services.MetaRequestFailed(
        exc.message or whatsapp_services.MetaRequestFailed.default_detail
    )


def require_catalog_access(waba: WhatsAppBusinessAccount) -> str:
    """The seller's Meta business id. Raises 409 ``catalog_permissions_missing`` when the token
    can't manage catalogs, and ``whatsapp_not_connected`` without a usable token."""
    ensure_connected(waba)
    if not whatsapp_services.catalog_permissions_granted(waba):
        raise CatalogPermissionsMissing()
    business_id = whatsapp_services.business_id_for(waba)
    if not business_id:
        raise CatalogPermissionsMissing()
    return business_id


def _catalog_rows(catalogs) -> list[dict]:
    return [
        {"id": str(catalog["id"]), "name": str(catalog.get("name") or "")}
        for catalog in catalogs
        if isinstance(catalog, dict) and catalog.get("id")
    ]


def available_catalogs(waba: WhatsAppBusinessAccount) -> list[dict]:
    """``AvailableCatalog`` rows: catalogs owned by the seller's Meta business."""
    business_id = require_catalog_access(waba)
    try:
        return _catalog_rows(get_client(waba.access_token).list_business_catalogs(business_id))
    except GraphAPIError as exc:
        raise meta_error(exc) from None


def connect_catalog(
    workspace, *, waba, user, catalog_id: str | None = None, create_name: str | None = None
) -> tuple[MetaCatalog, bool]:
    """Connect an owned catalog (or create one) to the WABA; returns ``(catalog, created)``.

    Refreshes the commerce settings of the WABA's numbers and queues a full sync.
    """
    business_id = require_catalog_access(waba)
    client = get_client(waba.access_token)
    try:
        if create_name:
            catalog_id = str(client.create_catalog(business_id, name=create_name)["id"])
            catalog_name = create_name
        else:
            owned = {
                row["id"]: row for row in _catalog_rows(client.list_business_catalogs(business_id))
            }
            if catalog_id not in owned:
                raise serializers.ValidationError(
                    {"catalog_id": ["This catalog is not owned by your Meta business."]}
                )
            catalog_name = owned[catalog_id]["name"]
        connected = {row["id"] for row in _catalog_rows(client.list_waba_catalogs(waba.waba_id))}
        if catalog_id not in connected:
            client.connect_catalog(waba.waba_id, catalog_id)
    except GraphAPIError as exc:
        raise meta_error(exc) from None

    with transaction.atomic():
        meta_catalog = MetaCatalog.objects.select_for_update().filter(waba=waba).first()
        created = meta_catalog is None
        if created:
            meta_catalog = MetaCatalog(workspace=workspace, waba=waba)
        elif meta_catalog.catalog_id != catalog_id:
            # Another catalog: nothing of ours is in it yet.
            meta_catalog.last_synced_at = None
            CatalogSyncBatch.objects.filter(meta_catalog=meta_catalog).delete()
            _reset_product_sync(workspace.pk)
        meta_catalog.catalog_id = catalog_id
        meta_catalog.catalog_name = catalog_name[:255]
        meta_catalog.business_id = business_id
        meta_catalog.status = MetaCatalog.Status.CONNECTED
        meta_catalog.last_sync_error = ""
        meta_catalog.connected_by = user
        meta_catalog.save()
        refresh_commerce_settings(meta_catalog, client)
        sync.queue_full_sync(meta_catalog)
    return meta_catalog, created


def _reset_product_sync(workspace_id) -> None:
    Product.objects.filter(workspace_id=workspace_id).update(
        meta_sync_status=Product.SyncStatus.NOT_SYNCED,
        meta_review_status=Product.ReviewStatus.NONE,
        meta_rejection_reasons=[],
        meta_product_id="",
        meta_synced_at=None,
        meta_sync_error="",
    )


def disconnect_catalog(meta_catalog: MetaCatalog) -> None:
    """Forget the catalog locally; Meta keeps it. The store falls back to bot mode."""
    workspace_id = meta_catalog.workspace_id
    with transaction.atomic():
        meta_catalog.delete()
        if not MetaCatalog.objects.filter(workspace_id=workspace_id).exists():
            _reset_product_sync(workspace_id)


def resync(meta_catalog: MetaCatalog) -> MetaCatalog:
    """Queue a full resync, re-checking permissions of a catalog that lost them."""
    waba = meta_catalog.waba
    if meta_catalog.status != MetaCatalog.Status.CONNECTED:
        require_catalog_access(waba)
        meta_catalog.status = MetaCatalog.Status.CONNECTED
        meta_catalog.last_sync_error = ""
        meta_catalog.save(update_fields=["status", "last_sync_error", "updated_at"])
    else:
        ensure_connected(waba)
    sync.queue_full_sync(meta_catalog)
    return meta_catalog


def _store_setting(meta_catalog: MetaCatalog, number: PhoneNumber, *, cart: bool, visible: bool):
    MetaCatalogPhoneSetting.objects.update_or_create(
        phone_number=number,
        defaults={
            "workspace_id": meta_catalog.workspace_id,
            "meta_catalog": meta_catalog,
            "is_cart_enabled": cart,
            "is_catalog_visible": visible,
            "last_synced_at": timezone.now(),
        },
    )


def refresh_commerce_settings(meta_catalog: MetaCatalog, client) -> None:
    """Store Meta's cart and visibility flags for each number on the WABA (best effort)."""
    numbers = PhoneNumber.objects.filter(
        workspace_id=meta_catalog.workspace_id, waba_id=meta_catalog.waba_id
    )
    for number in numbers:
        try:
            data = client.get_commerce_settings(number.phone_number_id)
        except GraphAPIError as exc:
            logger.warning(
                "Commerce settings of number %s could not be read: %s",
                number.phone_number_id,
                type(exc).__name__,
            )
            continue
        _store_setting(
            meta_catalog,
            number,
            cart=bool(data.get("is_cart_enabled")),
            visible=bool(data.get("is_catalog_visible")),
        )


def update_commerce_settings(
    meta_catalog: MetaCatalog,
    *,
    phone_number_id,
    is_cart_enabled: bool | None = None,
    is_catalog_visible: bool | None = None,
) -> None:
    """Change cart/catalog visibility of one number on the catalog's WABA (both on Meta and
    locally). Without flags the stored values are refreshed from Meta."""
    number = PhoneNumber.objects.filter(
        workspace_id=meta_catalog.workspace_id, waba_id=meta_catalog.waba_id, pk=phone_number_id
    ).first()
    if number is None:
        raise serializers.ValidationError(
            {"phone_number_id": ["This number is not on the catalog's WhatsApp Business Account."]}
        )
    waba = meta_catalog.waba
    ensure_connected(waba)
    client = get_client(waba.access_token)
    stored = MetaCatalogPhoneSetting.objects.filter(phone_number=number).first()
    try:
        if stored is None or (is_cart_enabled is None and is_catalog_visible is None):
            current = client.get_commerce_settings(number.phone_number_id)
            cart = bool(current.get("is_cart_enabled"))
            visible = bool(current.get("is_catalog_visible"))
        else:
            cart, visible = stored.is_cart_enabled, stored.is_catalog_visible
        if is_cart_enabled is not None or is_catalog_visible is not None:
            client.update_commerce_settings(
                number.phone_number_id,
                is_cart_enabled=is_cart_enabled,
                is_catalog_visible=is_catalog_visible,
            )
    except GraphAPIError as exc:
        raise meta_error(exc) from None
    _store_setting(
        meta_catalog,
        number,
        cart=cart if is_cart_enabled is None else is_cart_enabled,
        visible=visible if is_catalog_visible is None else is_catalog_visible,
    )
