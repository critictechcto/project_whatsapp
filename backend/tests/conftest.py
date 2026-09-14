"""Shared fixtures for cross-app end-to-end tests: a connected number and signed Meta webhooks."""

import hashlib
import hmac
import json

import pytest
from django.conf import settings
from django.urls import reverse

from apps.billing.plans import ensure_default_plans
from apps.whatsapp.factories import PhoneNumberFactory

WABA_ID = "102290129340398"
PHONE_NUMBER_ID = "106540352242922"
DISPLAY_PHONE_NUMBER = "15550783881"
CUSTOMER_WA_ID = "919876543210"


@pytest.fixture(autouse=True)
def _default_plans(request):
    """Transactional tests flush the migration-seeded plans; restore them for every DB test."""
    marker = request.node.get_closest_marker("django_db")
    if marker is None:
        return
    request.getfixturevalue("transactional_db" if marker.kwargs.get("transaction") else "db")
    ensure_default_plans()


@pytest.fixture
def e2e_number(workspace):
    """The workspace's default number, addressed by the Meta ids the payload helpers use."""
    return PhoneNumberFactory(
        workspace=workspace,
        waba__workspace=workspace,
        waba__waba_id=WABA_ID,
        phone_number_id=PHONE_NUMBER_ID,
        display_phone_number=DISPLAY_PHONE_NUMBER,
        is_default=True,
    )


def signed_meta_request(payload: dict) -> dict:
    """Keyword arguments for ``client.post`` delivering ``payload`` as Meta would."""
    body = json.dumps(payload).encode()
    digest = hmac.new(settings.META_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {
        "path": reverse("webhooks:meta-callback"),
        "data": body,
        "content_type": "application/json",
        "headers": {"X-Hub-Signature-256": f"sha256={digest}"},
    }


@pytest.fixture
def deliver_meta(client, django_capture_on_commit_callbacks):
    """POST a signed Meta webhook and run everything it queues on commit (Celery is eager)."""

    def deliver(payload: dict) -> None:
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(**signed_meta_request(payload))
        assert response.status_code == 200, response.content

    return deliver


def messages_payload(*, entry_time: int | None = None, **value) -> dict:
    entry: dict = {
        "id": WABA_ID,
        "changes": [
            {
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": DISPLAY_PHONE_NUMBER,
                        "phone_number_id": PHONE_NUMBER_ID,
                    },
                    **value,
                },
            }
        ],
    }
    if entry_time is not None:
        entry["time"] = entry_time
    return {"object": "whatsapp_business_account", "entry": [entry]}


def inbound_text(
    text: str,
    wamid: str,
    timestamp: int,
    *,
    wa_id: str = CUSTOMER_WA_ID,
    name: str = "Priya Sharma",
    entry_time: int | None = None,
) -> dict:
    return messages_payload(
        entry_time=entry_time,
        contacts=[{"profile": {"name": name}, "wa_id": wa_id}],
        messages=[
            {
                "from": wa_id,
                "id": wamid,
                "timestamp": str(timestamp),
                "type": "text",
                "text": {"body": text},
            }
        ],
    )


def status_update(
    wamid: str, status: str, timestamp: int, *, wa_id: str, error_code: int | None = None
) -> dict:
    entry = {
        "id": wamid,
        "status": status,
        "timestamp": str(timestamp),
        "recipient_id": wa_id,
    }
    if error_code is not None:
        entry["errors"] = [{"code": error_code, "title": "Message undeliverable"}]
    return messages_payload(statuses=[entry])
