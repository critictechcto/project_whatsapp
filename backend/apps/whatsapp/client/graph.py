"""Real Graph API client over httpx. Stub: implemented by the whatsapp app in wave 1.

Keep method signatures identical to ``GraphClient`` (enforced by the contract test).
"""

import httpx

from .base import JSON


class HttpGraphClient:
    def __init__(
        self, access_token: str | None = None, *, http_client: httpx.Client | None = None
    ) -> None:
        self.access_token = access_token
        self._http = http_client

    def exchange_code(self, code: str) -> JSON:
        raise NotImplementedError

    def debug_token(self, input_token: str) -> JSON:
        raise NotImplementedError

    def get_waba(self, waba_id: str) -> JSON:
        raise NotImplementedError

    def list_phone_numbers(self, waba_id: str) -> list[JSON]:
        raise NotImplementedError

    def get_phone_number(self, phone_number_id: str) -> JSON:
        raise NotImplementedError

    def subscribe_app(self, waba_id: str) -> JSON:
        raise NotImplementedError

    def unsubscribe_app(self, waba_id: str) -> JSON:
        raise NotImplementedError

    def register_phone(self, phone_number_id: str, pin: str) -> JSON:
        raise NotImplementedError

    def deregister_phone(self, phone_number_id: str) -> JSON:
        raise NotImplementedError

    def send_message(self, phone_number_id: str, message: JSON) -> JSON:
        raise NotImplementedError

    def mark_read(
        self, phone_number_id: str, wamid: str, *, typing_indicator: bool = False
    ) -> JSON:
        raise NotImplementedError

    def upload_media(
        self, phone_number_id: str, *, content: bytes, mime_type: str, filename: str
    ) -> JSON:
        raise NotImplementedError

    def get_media(self, media_id: str) -> JSON:
        raise NotImplementedError

    def download_media(self, url: str) -> bytes:
        raise NotImplementedError

    def list_templates(self, waba_id: str, *, after: str | None = None, limit: int = 100) -> JSON:
        raise NotImplementedError

    def create_template(self, waba_id: str, template: JSON) -> JSON:
        raise NotImplementedError

    def delete_template(self, waba_id: str, *, name: str, template_id: str | None = None) -> JSON:
        raise NotImplementedError
