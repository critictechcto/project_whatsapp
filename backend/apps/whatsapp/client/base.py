"""The GraphClient contract. Both HttpGraphClient and FakeGraphClient implement it exactly
(a contract test compares signatures). Methods return Meta's JSON as dicts and raise
subclasses of :class:`~apps.whatsapp.client.errors.GraphAPIError`.
"""

from typing import Any, Protocol, runtime_checkable

JSON = dict[str, Any]


@runtime_checkable
class GraphClient(Protocol):
    access_token: str | None

    # --- App-level calls (use META_APP_ID / META_APP_SECRET, no customer token) -------------

    def exchange_code(self, code: str) -> JSON:
        """Embedded Signup code → business token.

        ``GET /oauth/access_token?client_id&client_secret&code`` →
        ``{"access_token": str, "token_type": "bearer", "expires_in"?: int}``
        """
        ...

    def debug_token(self, input_token: str) -> JSON:
        """Inspect a token with the app token (``APP_ID|APP_SECRET``).

        ``GET /debug_token?input_token`` → the unwrapped ``data`` object:
        ``{"app_id", "type", "is_valid", "expires_at", "scopes": [...],
        "granular_scopes": [{"scope": str, "target_ids": [str]}]}``
        """
        ...

    # --- Business account (customer token) --------------------------------------------------

    def get_waba(self, waba_id: str) -> JSON:
        """``GET /{waba_id}`` → ``{"id", "name", "currency", "timezone_id",
        "message_template_namespace", ...}``"""
        ...

    def list_phone_numbers(self, waba_id: str) -> list[JSON]:
        """``GET /{waba_id}/phone_numbers`` → phone number objects, as in get_phone_number."""
        ...

    def get_phone_number(self, phone_number_id: str) -> JSON:
        """``GET /{phone_number_id}`` → ``{"id", "display_phone_number", "verified_name",
        "quality_rating", "code_verification_status", "platform_type", "name_status", "status",
        "throughput": {"level"}, "messaging_limit_tier"?}``"""
        ...

    def subscribe_app(self, waba_id: str) -> JSON:
        """``POST /{waba_id}/subscribed_apps`` → ``{"success": true}``"""
        ...

    def unsubscribe_app(self, waba_id: str) -> JSON:
        """``DELETE /{waba_id}/subscribed_apps`` → ``{"success": true}``"""
        ...

    def register_phone(self, phone_number_id: str, pin: str) -> JSON:
        """``POST /{phone_number_id}/register`` with the 6-digit two-step PIN.

        → ``{"success": true}``
        """
        ...

    def deregister_phone(self, phone_number_id: str) -> JSON:
        """``POST /{phone_number_id}/deregister`` → ``{"success": true}``"""
        ...

    # --- Messaging ------------------------------------------------------------------------------

    def send_message(self, phone_number_id: str, message: JSON) -> JSON:
        """``POST /{phone_number_id}/messages``. ``message`` is the Cloud API body without
        ``messaging_product`` (the client adds it), e.g. ``{"to", "type": "template", "template"}``.
        → ``{"messaging_product": "whatsapp", "contacts": [{"input", "wa_id"}],
        "messages": [{"id": "wamid..."}]}``"""
        ...

    def mark_read(
        self, phone_number_id: str, wamid: str, *, typing_indicator: bool = False
    ) -> JSON:
        """``POST /{phone_number_id}/messages`` with ``status: read`` → ``{"success": true}``"""
        ...

    def upload_media(
        self, phone_number_id: str, *, content: bytes, mime_type: str, filename: str
    ) -> JSON:
        """``POST /{phone_number_id}/media`` (multipart) → ``{"id": media_id}``"""
        ...

    def get_media(self, media_id: str) -> JSON:
        """``GET /{media_id}`` → ``{"id", "url", "mime_type", "sha256", "file_size"}``.
        The URL expires after a few minutes."""
        ...

    def download_media(self, url: str) -> bytes:
        """``GET`` a media URL from get_media, authenticated with the token."""
        ...

    # --- Templates ------------------------------------------------------------------------------

    def list_templates(self, waba_id: str, *, after: str | None = None, limit: int = 100) -> JSON:
        """``GET /{waba_id}/message_templates`` → ``{"data": [template...],
        "paging": {"cursors": {"before", "after"}, "next"?}}``. Each template has ``id, name,
        language, category, status, components, quality_score?, rejected_reason?``."""
        ...

    def create_template(self, waba_id: str, template: JSON) -> JSON:
        """``POST /{waba_id}/message_templates`` with ``{"name", "language", "category",
        "components"}`` → ``{"id", "status", "category"}``"""
        ...

    def delete_template(self, waba_id: str, *, name: str, template_id: str | None = None) -> JSON:
        """``DELETE /{waba_id}/message_templates?name[&hsm_id]`` → ``{"success": true}``.
        Without ``template_id`` every language of ``name`` is deleted."""
        ...

    def edit_message_template(
        self, template_id: str, *, components: list[JSON], category: str | None = None
    ) -> JSON:
        """``POST /{template_id}`` with ``{"components", "category"?}`` → ``{"success": true}``.

        Meta rules (https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-management):
        only ``APPROVED``, ``REJECTED`` or ``PAUSED`` templates can be edited (a template in review
        fails with subcode 2388039); only the category, components and TTL can change, and the
        category of an ``APPROVED`` template can't. ``components`` replaces every component. An
        ``APPROVED`` template can be edited once per 24 hours and 10 times per 30 days; rejected
        and paused ones without limit. Edited approved or paused templates are re-approved
        automatically unless they fail review."""
        ...

    # --- Commerce: catalogs (needs catalog_management + business_management) ---------------

    def list_waba_catalogs(self, waba_id: str) -> list[JSON]:
        """``GET /{waba_id}/product_catalogs`` (all pages) → catalogs connected to the WABA:
        ``[{"id", "name"}]``. Meta allows one connected catalog per WABA."""
        ...

    def list_business_catalogs(self, business_id: str) -> list[JSON]:
        """``GET /{business_id}/owned_product_catalogs`` (all pages) → catalogs the seller's
        business owns: ``[{"id", "name", "vertical"}]``. ``business_id`` is
        ``owner_business_info.id`` from get_waba."""
        ...

    def create_catalog(self, business_id: str, *, name: str) -> JSON:
        """``POST /{business_id}/owned_product_catalogs`` with ``{"name", "vertical": "commerce"}``
        → ``{"id"}``"""
        ...

    def connect_catalog(self, waba_id: str, catalog_id: str) -> JSON:
        """``POST /{waba_id}/product_catalogs`` with ``{"catalog_id"}`` → ``{"success": true}``"""
        ...

    def batch_catalog_items(self, catalog_id: str, requests: list[JSON]) -> JSON:
        """``POST /{catalog_id}/items_batch`` with ``{"item_type": "PRODUCT_ITEM",
        "allow_upsert": true, "requests": [{"method": "CREATE"|"UPDATE"|"DELETE",
        "data": {"id": retailer_id, "title", "description", "availability", "condition",
        "price": "249.00 INR", "sale_price"?, "link", "image_link", "brand"}}]}`` (≤ 5,000
        requests; new catalogs allow about 8 calls a minute, error 80014 when exceeded) →
        ``{"handles": [str], "validation_status"?: [{"retailer_id", "errors": [{"message"}]}]}``"""
        ...

    def get_catalog_batch_status(self, catalog_id: str, handle: str) -> JSON:
        """``GET /{catalog_id}/check_batch_request_status?handle`` → ``{"data": [{"handle",
        "status": "started"|"in_progress"|"finished"|"error", "errors_total_count",
        "errors": [{"line", "id", "message"}], "warnings": [...]}]}``"""
        ...

    def list_catalog_products(
        self, catalog_id: str, *, after: str | None = None, limit: int = 100
    ) -> JSON:
        """``GET /{catalog_id}/products?fields=id,retailer_id,name,availability,review_status,
        review_rejection_reasons`` → ``{"data": [product...], "paging": {"cursors", "next"?}}``.
        ``review_status`` is ``pending``, ``rejected``, ``approved`` or ``outdated``."""
        ...

    def get_commerce_settings(self, phone_number_id: str) -> JSON:
        """``GET /{phone_number_id}/whatsapp_commerce_settings`` → the unwrapped first ``data``
        item: ``{"id", "is_cart_enabled", "is_catalog_visible"}`` (Meta defaults: cart on,
        catalog hidden)."""
        ...

    def update_commerce_settings(
        self,
        phone_number_id: str,
        *,
        is_cart_enabled: bool | None = None,
        is_catalog_visible: bool | None = None,
    ) -> JSON:
        """``POST /{phone_number_id}/whatsapp_commerce_settings?is_cart_enabled&is_catalog_visible``
        (only the given flags) → ``{"success": true}``"""
        ...
