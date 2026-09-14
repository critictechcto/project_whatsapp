"""In-memory GraphClient for tests. Seed state with the ``add_*`` helpers, script failures with
:meth:`FakeGraphClient.fail`, and assert on ``calls`` / ``sent_messages``."""

import copy
import hashlib
import itertools
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

from .base import JSON
from .errors import GraphAPIError, InvalidParameterError


@dataclass
class FakeCall:
    method: str
    kwargs: dict[str, Any] = field(default_factory=dict)
    access_token: str | None = None


class FakeGraphClient:
    def __init__(self, access_token: str | None = None) -> None:
        self.access_token = access_token
        self.calls: list[FakeCall] = []
        self.wabas: dict[str, JSON] = {}
        self.phone_numbers: dict[str, JSON] = {}
        self.templates: dict[str, JSON] = {}
        self.subscribed_waba_ids: set[str] = set()
        self.registered_pins: dict[str, str] = {}
        self.sent_messages: list[JSON] = []
        self.media: dict[str, JSON] = {}
        self._codes: dict[str, str] = {}
        self._token_debug: dict[str, JSON] = {}
        self._phone_waba: dict[str, str] = {}
        self._template_waba: dict[str, str] = {}
        self.catalogs: dict[str, JSON] = {}
        # catalog id -> retailer id -> product (as list_catalog_products returns it)
        self.catalog_products: dict[str, dict[str, JSON]] = defaultdict(dict)
        self.catalog_batches: dict[str, JSON] = {}
        self.commerce_settings: dict[str, JSON] = {}
        self._catalog_business: dict[str, str] = {}
        self._waba_catalog: dict[str, str] = {}
        self._failures: dict[str, list[GraphAPIError]] = defaultdict(list)
        self._ids = itertools.count(1)

    # --- Test setup helpers -------------------------------------------------------------------

    def add_waba(self, waba_id: str, **fields: Any) -> JSON:
        self.wabas[waba_id] = {
            "id": waba_id,
            "name": "Test Business",
            "currency": "INR",
            "timezone_id": "71",
            "message_template_namespace": f"ns_{waba_id}",
            **fields,
        }
        return self.wabas[waba_id]

    def add_phone_number(
        self,
        waba_id: str,
        phone_number_id: str,
        *,
        display_phone_number: str = "+91 98000 41207",
        **fields: Any,
    ) -> JSON:
        if waba_id not in self.wabas:
            self.add_waba(waba_id)
        self.phone_numbers[phone_number_id] = {
            "id": phone_number_id,
            "display_phone_number": display_phone_number,
            "verified_name": "Test Business",
            "quality_rating": "GREEN",
            "code_verification_status": "VERIFIED",
            "platform_type": "CLOUD_API",
            "name_status": "APPROVED",
            "status": "CONNECTED",
            "throughput": {"level": "STANDARD"},
            "messaging_limit_tier": "TIER_1K",
            **fields,
        }
        self._phone_waba[phone_number_id] = waba_id
        return self.phone_numbers[phone_number_id]

    def add_signup(
        self,
        code: str,
        *,
        waba_id: str,
        token: str | None = None,
        target_ids: list[str] | None = None,
    ) -> str:
        """Make ``code`` exchangeable for a token whose granular scopes cover ``waba_id``."""
        token = token or f"EAAG-fake-business-token-{next(self._ids)}"
        targets = target_ids if target_ids is not None else [waba_id]
        self._codes[code] = token
        self._token_debug[token] = {
            "app_id": settings.META_APP_ID,
            "type": "SYSTEM_USER",
            "application": "UpChatz",
            "is_valid": True,
            "expires_at": 0,
            "data_access_expires_at": 0,
            "scopes": ["whatsapp_business_management", "whatsapp_business_messaging"],
            "granular_scopes": [
                {"scope": "whatsapp_business_management", "target_ids": list(targets)},
                {"scope": "whatsapp_business_messaging", "target_ids": list(targets)},
            ],
        }
        return token

    def add_template(self, waba_id: str, **fields: Any) -> JSON:
        template_id = fields.pop("id", None) or str(900000 + next(self._ids))
        self.templates[template_id] = {
            "id": template_id,
            "name": "order_update",
            "language": "en",
            "category": "UTILITY",
            "status": "APPROVED",
            "components": [{"type": "BODY", "text": "Hello {{1}}"}],
            **fields,
        }
        self._template_waba[template_id] = waba_id
        return self.templates[template_id]

    def add_catalog(
        self,
        catalog_id: str,
        *,
        business_id: str = "5550001",
        waba_id: str | None = None,
        name: str = "Test Catalog",
    ) -> JSON:
        """Seed a catalog owned by ``business_id``, connected to ``waba_id`` when given."""
        self.catalogs[catalog_id] = {"id": catalog_id, "name": name, "vertical": "commerce"}
        self._catalog_business[catalog_id] = business_id
        if waba_id is not None:
            self._waba_catalog[waba_id] = catalog_id
        return self.catalogs[catalog_id]

    def set_product_review(
        self,
        catalog_id: str,
        retailer_id: str,
        review_status: str,
        reasons: list[str] | None = None,
    ) -> None:
        product = self.catalog_products[catalog_id][retailer_id]
        product["review_status"] = review_status
        product["review_rejection_reasons"] = list(reasons or [])

    def fail(self, method: str, error: GraphAPIError, *, times: int = 1) -> None:
        """Raise ``error`` on the next ``times`` calls to ``method``."""
        self._failures[method].extend([error] * times)

    def calls_to(self, method: str) -> list[FakeCall]:
        return [call for call in self.calls if call.method == method]

    # --- Internals ------------------------------------------------------------------------------

    def _record(self, method: str, **kwargs: Any) -> None:
        self.calls.append(FakeCall(method, kwargs, self.access_token))
        queue = self._failures.get(method)
        if queue:
            raise queue.pop(0)

    @staticmethod
    def _not_found(object_id: str) -> InvalidParameterError:
        return InvalidParameterError(
            f"Unsupported get request. Object with ID '{object_id}' does not exist.",
            http_status=400,
            code=100,
            subcode=33,
        )

    # --- GraphClient ------------------------------------------------------------------------------

    def exchange_code(self, code: str) -> JSON:
        self._record("exchange_code", code=code)
        if code not in self._codes:
            raise InvalidParameterError(
                "Invalid verification code format.", http_status=400, code=100
            )
        return {"access_token": self._codes[code], "token_type": "bearer"}

    def debug_token(self, input_token: str) -> JSON:
        self._record("debug_token", input_token=input_token)
        data = self._token_debug.get(input_token)
        if data is None:
            return {
                "app_id": settings.META_APP_ID,
                "is_valid": False,
                "scopes": [],
                "granular_scopes": [],
            }
        return copy.deepcopy(data)

    def get_waba(self, waba_id: str) -> JSON:
        self._record("get_waba", waba_id=waba_id)
        if waba_id not in self.wabas:
            raise self._not_found(waba_id)
        return copy.deepcopy(self.wabas[waba_id])

    def list_phone_numbers(self, waba_id: str) -> list[JSON]:
        self._record("list_phone_numbers", waba_id=waba_id)
        return [
            copy.deepcopy(phone)
            for phone_id, phone in self.phone_numbers.items()
            if self._phone_waba.get(phone_id) == waba_id
        ]

    def get_phone_number(self, phone_number_id: str) -> JSON:
        self._record("get_phone_number", phone_number_id=phone_number_id)
        if phone_number_id not in self.phone_numbers:
            raise self._not_found(phone_number_id)
        return copy.deepcopy(self.phone_numbers[phone_number_id])

    def subscribe_app(self, waba_id: str) -> JSON:
        self._record("subscribe_app", waba_id=waba_id)
        self.subscribed_waba_ids.add(waba_id)
        return {"success": True}

    def unsubscribe_app(self, waba_id: str) -> JSON:
        self._record("unsubscribe_app", waba_id=waba_id)
        self.subscribed_waba_ids.discard(waba_id)
        return {"success": True}

    def register_phone(self, phone_number_id: str, pin: str) -> JSON:
        self._record("register_phone", phone_number_id=phone_number_id, pin=pin)
        if phone_number_id not in self.phone_numbers:
            raise self._not_found(phone_number_id)
        self.registered_pins[phone_number_id] = pin
        return {"success": True}

    def deregister_phone(self, phone_number_id: str) -> JSON:
        self._record("deregister_phone", phone_number_id=phone_number_id)
        self.registered_pins.pop(phone_number_id, None)
        return {"success": True}

    def send_message(self, phone_number_id: str, message: JSON) -> JSON:
        self._record("send_message", phone_number_id=phone_number_id, message=message)
        wamid = f"wamid.FAKE{next(self._ids):010d}"
        recipient = str(message.get("to", ""))
        self.sent_messages.append(
            {"phone_number_id": phone_number_id, "wamid": wamid, **copy.deepcopy(message)}
        )
        return {
            "messaging_product": "whatsapp",
            "contacts": [{"input": recipient, "wa_id": recipient.removeprefix("+")}],
            "messages": [{"id": wamid}],
        }

    def mark_read(
        self, phone_number_id: str, wamid: str, *, typing_indicator: bool = False
    ) -> JSON:
        self._record(
            "mark_read",
            phone_number_id=phone_number_id,
            wamid=wamid,
            typing_indicator=typing_indicator,
        )
        return {"success": True}

    def upload_media(
        self, phone_number_id: str, *, content: bytes, mime_type: str, filename: str
    ) -> JSON:
        self._record(
            "upload_media", phone_number_id=phone_number_id, mime_type=mime_type, filename=filename
        )
        media_id = str(700000 + next(self._ids))
        self.media[media_id] = {
            "id": media_id,
            "url": f"https://lookaside.fbsbx.com/whatsapp_business/attachments/?mid={media_id}",
            "mime_type": mime_type,
            "sha256": hashlib.sha256(content).hexdigest(),
            "file_size": len(content),
            "content": content,
        }
        return {"id": media_id}

    def get_media(self, media_id: str) -> JSON:
        self._record("get_media", media_id=media_id)
        if media_id not in self.media:
            raise self._not_found(media_id)
        item = self.media[media_id]
        return {
            "messaging_product": "whatsapp",
            **{k: v for k, v in item.items() if k != "content"},
        }

    def download_media(self, url: str) -> bytes:
        self._record("download_media", url=url)
        for item in self.media.values():
            if item["url"] == url:
                return item["content"]
        return b"fake-media-bytes"

    def list_templates(self, waba_id: str, *, after: str | None = None, limit: int = 100) -> JSON:
        self._record("list_templates", waba_id=waba_id, after=after, limit=limit)
        items = [
            copy.deepcopy(template)
            for template_id, template in self.templates.items()
            if self._template_waba.get(template_id) == waba_id
        ]
        start = int(after) if after else 0
        page = items[start : start + limit]
        end = start + len(page)
        paging: JSON = {"cursors": {"before": str(start), "after": str(end)}}
        if end < len(items):
            paging["next"] = (
                f"https://graph.facebook.com/fake/{waba_id}/message_templates?after={end}"
            )
        return {"data": page, "paging": paging}

    def create_template(self, waba_id: str, template: JSON) -> JSON:
        self._record("create_template", waba_id=waba_id, template=template)
        created = self.add_template(
            waba_id,
            name=template["name"],
            language=template["language"],
            category=template["category"],
            components=copy.deepcopy(template.get("components", [])),
            status="PENDING",
        )
        return {"id": created["id"], "status": "PENDING", "category": created["category"]}

    def delete_template(self, waba_id: str, *, name: str, template_id: str | None = None) -> JSON:
        self._record("delete_template", waba_id=waba_id, name=name, template_id=template_id)
        matches = [
            existing_id
            for existing_id, template in self.templates.items()
            if self._template_waba.get(existing_id) == waba_id
            and template["name"] == name
            and (template_id is None or existing_id == template_id)
        ]
        if not matches:
            raise InvalidParameterError("Message template not found.", http_status=400, code=100)
        for existing_id in matches:
            del self.templates[existing_id]
            del self._template_waba[existing_id]
        return {"success": True}

    # --- Commerce: catalogs ---------------------------------------------------------------------

    def _catalog(self, catalog_id: str) -> JSON:
        if catalog_id not in self.catalogs:
            raise self._not_found(catalog_id)
        return self.catalogs[catalog_id]

    def list_waba_catalogs(self, waba_id: str) -> list[JSON]:
        self._record("list_waba_catalogs", waba_id=waba_id)
        catalog_id = self._waba_catalog.get(waba_id)
        if catalog_id is None:
            return []
        catalog = self._catalog(catalog_id)
        return [{"id": catalog["id"], "name": catalog["name"]}]

    def list_business_catalogs(self, business_id: str) -> list[JSON]:
        self._record("list_business_catalogs", business_id=business_id)
        return [
            copy.deepcopy(catalog)
            for catalog_id, catalog in self.catalogs.items()
            if self._catalog_business.get(catalog_id) == business_id
        ]

    def create_catalog(self, business_id: str, *, name: str) -> JSON:
        self._record("create_catalog", business_id=business_id, name=name)
        catalog_id = str(800000 + next(self._ids))
        self.add_catalog(catalog_id, business_id=business_id, name=name)
        return {"id": catalog_id}

    def connect_catalog(self, waba_id: str, catalog_id: str) -> JSON:
        self._record("connect_catalog", waba_id=waba_id, catalog_id=catalog_id)
        self._catalog(catalog_id)
        self._waba_catalog[waba_id] = catalog_id
        return {"success": True}

    def batch_catalog_items(self, catalog_id: str, requests: list[JSON]) -> JSON:
        self._record("batch_catalog_items", catalog_id=catalog_id, requests=requests)
        self._catalog(catalog_id)
        products = self.catalog_products[catalog_id]
        for request in requests:
            data = request.get("data") or {}
            retailer_id = str(data.get("id", ""))
            if request.get("method") == "DELETE":
                products.pop(retailer_id, None)
                continue
            existing = products.get(retailer_id)
            products[retailer_id] = {
                "id": existing["id"] if existing else str(600000 + next(self._ids)),
                "retailer_id": retailer_id,
                "name": data.get("title", existing["name"] if existing else ""),
                "availability": data.get("availability", "in stock"),
                "review_status": "pending",
                "review_rejection_reasons": [],
            }
        handle = f"fake-batch-{next(self._ids)}"
        self.catalog_batches[handle] = {
            "handle": handle,
            "status": "finished",
            "errors_total_count": 0,
            "errors": [],
            "warnings": [],
        }
        return {"handles": [handle]}

    def get_catalog_batch_status(self, catalog_id: str, handle: str) -> JSON:
        self._record("get_catalog_batch_status", catalog_id=catalog_id, handle=handle)
        if handle not in self.catalog_batches:
            raise self._not_found(handle)
        return {"data": [copy.deepcopy(self.catalog_batches[handle])]}

    def list_catalog_products(
        self, catalog_id: str, *, after: str | None = None, limit: int = 100
    ) -> JSON:
        self._record("list_catalog_products", catalog_id=catalog_id, after=after, limit=limit)
        self._catalog(catalog_id)
        items = [copy.deepcopy(product) for product in self.catalog_products[catalog_id].values()]
        start = int(after) if after else 0
        page = items[start : start + limit]
        end = start + len(page)
        paging: JSON = {"cursors": {"before": str(start), "after": str(end)}}
        if end < len(items):
            paging["next"] = f"https://graph.facebook.com/fake/{catalog_id}/products?after={end}"
        return {"data": page, "paging": paging}

    def get_commerce_settings(self, phone_number_id: str) -> JSON:
        self._record("get_commerce_settings", phone_number_id=phone_number_id)
        settings_ = self.commerce_settings.setdefault(
            phone_number_id,
            {"id": f"cs-{phone_number_id}", "is_cart_enabled": True, "is_catalog_visible": False},
        )
        return copy.deepcopy(settings_)

    def update_commerce_settings(
        self,
        phone_number_id: str,
        *,
        is_cart_enabled: bool | None = None,
        is_catalog_visible: bool | None = None,
    ) -> JSON:
        self._record(
            "update_commerce_settings",
            phone_number_id=phone_number_id,
            is_cart_enabled=is_cart_enabled,
            is_catalog_visible=is_catalog_visible,
        )
        current = self.commerce_settings.setdefault(
            phone_number_id,
            {"id": f"cs-{phone_number_id}", "is_cart_enabled": True, "is_catalog_visible": False},
        )
        if is_cart_enabled is not None:
            current["is_cart_enabled"] = is_cart_enabled
        if is_catalog_visible is not None:
            current["is_catalog_visible"] = is_catalog_visible
        return {"success": True}
