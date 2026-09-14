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
