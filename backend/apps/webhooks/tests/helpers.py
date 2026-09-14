"""Payload loading, signing and signal-recording helpers for webhooks tests."""

import hashlib
import hmac
import json
from pathlib import Path

from django.urls import reverse

from common import events

PAYLOADS = Path(__file__).parent / "payloads"
TEST_APP_SECRET = "test-app-secret"

# Ids used by the JSON fixtures in payloads/.
WABA_ID = "102290129340398"
PHONE_NUMBER_ID = "106540352242922"
OTHER_WABA_ID = "109876543210987"
OTHER_PHONE_NUMBER_ID = "108765432109876"

ALL_SIGNALS = (
    events.inbound_message_received,
    events.message_status_updated,
    events.template_status_updated,
    events.template_category_updated,
    events.template_quality_updated,
    events.phone_number_quality_updated,
    events.account_updated,
    events.platform_inbound_message_received,
)


def callback_url() -> str:
    return reverse("webhooks:meta-callback")


def payload_bytes(name: str) -> bytes:
    return (PAYLOADS / name).read_bytes()


def load_payload(name: str) -> dict:
    return json.loads(payload_bytes(name))


def sign(body: bytes, secret: str = TEST_APP_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def post_webhook(client, body: bytes, signature: str | None = None, *, signed: bool = True):
    headers = {}
    if signature is not None:
        headers["X-Hub-Signature-256"] = signature
    elif signed:
        headers["X-Hub-Signature-256"] = sign(body)
    return client.post(callback_url(), data=body, content_type="application/json", headers=headers)


class Recorder:
    """Signal receiver that keeps every event it gets."""

    def __init__(self) -> None:
        self.events: list = []

    def __call__(self, sender, event, **kwargs) -> None:
        self.events.append(event)

    def of(self, event_class: type) -> list:
        return [event for event in self.events if isinstance(event, event_class)]
