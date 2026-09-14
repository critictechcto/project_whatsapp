"""Real Graph API client over httpx.

Keep method signatures identical to ``GraphClient`` (enforced by the contract test). Tokens,
app secrets and ``appsecret_proof`` values never appear in logs, exception messages or reprs.
"""

import hashlib
import hmac
from typing import Any
from urllib.parse import urlsplit

import httpx
from django.conf import settings

from .base import JSON
from .errors import (
    GraphAPIError,
    InvalidParameterError,
    NetworkError,
    TokenInvalidError,
    error_from_response,
)

PHONE_NUMBER_FIELDS = (
    "id,display_phone_number,verified_name,quality_rating,code_verification_status,"
    "platform_type,name_status,status,throughput,messaging_limit_tier"
)
WABA_FIELDS = "id,name,currency,timezone_id,message_template_namespace"
TEMPLATE_FIELDS = "id,name,language,category,status,components,quality_score,rejected_reason"

# Hosts that may receive the customer's token when downloading media.
MEDIA_HOST_SUFFIXES = (".fbsbx.com", ".facebook.com", ".fbcdn.net", ".whatsapp.net")

MAX_PAGES = 50


def appsecret_proof(access_token: str, app_secret: str) -> str:
    return hmac.new(app_secret.encode(), access_token.encode(), hashlib.sha256).hexdigest()


class HttpGraphClient:
    def __init__(
        self, access_token: str | None = None, *, http_client: httpx.Client | None = None
    ) -> None:
        self.access_token = access_token
        self._http = http_client or httpx.Client(timeout=settings.META_GRAPH_TIMEOUT_SECONDS)

    def __repr__(self) -> str:
        bound = "customer" if self.access_token else "app"
        return f"<HttpGraphClient {bound}>"

    # --- Internals ------------------------------------------------------------------------------

    @property
    def base_url(self) -> str:
        return f"{settings.META_GRAPH_BASE_URL.rstrip('/')}/{settings.META_GRAPH_API_VERSION}"

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _customer_auth(self) -> tuple[dict[str, str], dict[str, str]]:
        """Bearer header plus ``appsecret_proof`` query parameter for customer-token calls."""
        if not self.access_token:
            raise TokenInvalidError("No access token is configured for this Graph API call.")
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {}
        if settings.META_APP_SECRET:
            params["appsecret_proof"] = appsecret_proof(self.access_token, settings.META_APP_SECRET)
        return headers, params

    def _send(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            response = self._http.request(method, url, params=params, headers=headers, **kwargs)
        except httpx.TransportError as exc:
            # The httpx message may embed the URL (and its secrets): report the type only.
            raise NetworkError(f"Could not reach the Graph API ({type(exc).__name__}).") from None
        if not response.is_success:
            try:
                body = response.json()
            except ValueError:
                body = None
            raise error_from_response(response.status_code, body, response.headers)
        return response

    @staticmethod
    def _json(response: httpx.Response) -> JSON:
        try:
            body = response.json()
        except ValueError:
            raise GraphAPIError(
                "Graph API returned a response that is not JSON.", http_status=response.status_code
            ) from None
        if not isinstance(body, dict):
            raise GraphAPIError(
                "Graph API returned an unexpected response.", http_status=response.status_code
            )
        return body

    def _call(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> JSON:
        headers, auth_params = self._customer_auth()
        response = self._send(
            method,
            self._url(path),
            params={**(params or {}), **auth_params},
            headers=headers,
            **kwargs,
        )
        return self._json(response)

    def _app_call(self, path: str, params: dict[str, Any]) -> JSON:
        if not (settings.META_APP_ID and settings.META_APP_SECRET):
            raise GraphAPIError("META_APP_ID and META_APP_SECRET must be configured.")
        return self._json(self._send("GET", self._url(path), params=params))

    # --- App-level calls ------------------------------------------------------------------------

    def exchange_code(self, code: str) -> JSON:
        return self._app_call(
            "oauth/access_token",
            {
                "client_id": settings.META_APP_ID,
                "client_secret": settings.META_APP_SECRET,
                "code": code,
            },
        )

    def debug_token(self, input_token: str) -> JSON:
        body = self._app_call(
            "debug_token",
            {
                "input_token": input_token,
                "access_token": f"{settings.META_APP_ID}|{settings.META_APP_SECRET}",
            },
        )
        data = body.get("data")
        if not isinstance(data, dict):
            raise GraphAPIError("Graph API debug_token response has no data.")
        return data

    # --- Business account -----------------------------------------------------------------------

    def get_waba(self, waba_id: str) -> JSON:
        return self._call("GET", waba_id, params={"fields": WABA_FIELDS})

    def list_phone_numbers(self, waba_id: str) -> list[JSON]:
        numbers: list[JSON] = []
        page = self._call("GET", f"{waba_id}/phone_numbers", params={"fields": PHONE_NUMBER_FIELDS})
        for _ in range(MAX_PAGES):
            numbers.extend(item for item in page.get("data") or [] if isinstance(item, dict))
            next_url = (page.get("paging") or {}).get("next")
            if not next_url:
                break
            page = self._follow(next_url)
        return numbers

    def _follow(self, next_url: str) -> JSON:
        """Fetch a ``paging.next`` URL; the token is only sent back to the Graph host."""
        if urlsplit(next_url).netloc != urlsplit(self.base_url).netloc:
            raise InvalidParameterError("Graph API paging link points to an unexpected host.")
        headers, auth_params = self._customer_auth()
        # Keep the cursor query of the link and add our auth parameters to it.
        url = httpx.URL(next_url).copy_merge_params(auth_params)
        return self._json(self._send("GET", str(url), headers=headers))

    def get_phone_number(self, phone_number_id: str) -> JSON:
        return self._call("GET", phone_number_id, params={"fields": PHONE_NUMBER_FIELDS})

    def subscribe_app(self, waba_id: str) -> JSON:
        return self._call("POST", f"{waba_id}/subscribed_apps")

    def unsubscribe_app(self, waba_id: str) -> JSON:
        return self._call("DELETE", f"{waba_id}/subscribed_apps")

    def register_phone(self, phone_number_id: str, pin: str) -> JSON:
        return self._call(
            "POST",
            f"{phone_number_id}/register",
            json={"messaging_product": "whatsapp", "pin": pin},
        )

    def deregister_phone(self, phone_number_id: str) -> JSON:
        return self._call("POST", f"{phone_number_id}/deregister")

    # --- Messaging ------------------------------------------------------------------------------

    def send_message(self, phone_number_id: str, message: JSON) -> JSON:
        return self._call(
            "POST",
            f"{phone_number_id}/messages",
            json={**message, "messaging_product": "whatsapp"},
        )

    def mark_read(
        self, phone_number_id: str, wamid: str, *, typing_indicator: bool = False
    ) -> JSON:
        body: JSON = {"messaging_product": "whatsapp", "status": "read", "message_id": wamid}
        if typing_indicator:
            body["typing_indicator"] = {"type": "text"}
        return self._call("POST", f"{phone_number_id}/messages", json=body)

    def upload_media(
        self, phone_number_id: str, *, content: bytes, mime_type: str, filename: str
    ) -> JSON:
        return self._call(
            "POST",
            f"{phone_number_id}/media",
            data={"messaging_product": "whatsapp", "type": mime_type},
            files={"file": (filename, content, mime_type)},
        )

    def get_media(self, media_id: str) -> JSON:
        return self._call("GET", media_id)

    def download_media(self, url: str) -> bytes:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        graph_host = (urlsplit(self.base_url).hostname or "").lower()
        allowed = host == graph_host or any(
            host.endswith(suffix) or host == suffix.lstrip(".") for suffix in MEDIA_HOST_SUFFIXES
        )
        if parts.scheme != "https" or not allowed:
            raise InvalidParameterError("Media URL is not a Meta media host.")
        headers, _ = self._customer_auth()
        return self._send("GET", url, headers=headers).content

    # --- Templates ------------------------------------------------------------------------------

    def list_templates(self, waba_id: str, *, after: str | None = None, limit: int = 100) -> JSON:
        params: dict[str, Any] = {"fields": TEMPLATE_FIELDS, "limit": limit}
        if after:
            params["after"] = after
        return self._call("GET", f"{waba_id}/message_templates", params=params)

    def create_template(self, waba_id: str, template: JSON) -> JSON:
        return self._call("POST", f"{waba_id}/message_templates", json=template)

    def delete_template(self, waba_id: str, *, name: str, template_id: str | None = None) -> JSON:
        params = {"name": name}
        if template_id:
            params["hsm_id"] = template_id
        return self._call("DELETE", f"{waba_id}/message_templates", params=params)
