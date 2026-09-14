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
