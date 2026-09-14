import json
from unittest import mock

import pytest

from apps.webhooks.models import WebhookEvent
from apps.webhooks.tasks import process_event
from common import events

from .helpers import callback_url, payload_bytes, post_webhook, sign

pytestmark = pytest.mark.django_db


# --- GET verification -----------------------------------------------------------------------


def verify(client, **params):
    query = {"hub.mode": "subscribe", "hub.challenge": "1158201444", **params}
    return client.get(callback_url(), query)


def test_verify_subscription_returns_challenge(client):
    response = verify(client, **{"hub.verify_token": "test-verify-token"})

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")
    assert response.content == b"1158201444"


@pytest.mark.parametrize(
    "params",
    [
        {"hub.verify_token": "wrong-token"},
        {"hub.verify_token": ""},
        {},
        {"hub.verify_token": "test-verify-token", "hub.mode": "unsubscribe"},
    ],
)
def test_verify_subscription_rejects_bad_requests(client, params):
    assert verify(client, **params).status_code == 403


def test_verify_subscription_rejects_when_token_not_configured(client, settings):
    settings.META_WEBHOOK_VERIFY_TOKEN = ""

    assert verify(client, **{"hub.verify_token": ""}).status_code == 403


# --- POST signature and body ----------------------------------------------------------------


def test_signed_post_stores_event_and_enqueues_on_commit(
    client, django_capture_on_commit_callbacks
):
    body = payload_bytes("text_message.json")

    with django_capture_on_commit_callbacks() as callbacks:
        response = post_webhook(client, body)

    assert response.status_code == 200
    event = WebhookEvent.objects.get()
    assert event.status == WebhookEvent.Status.RECEIVED
    assert event.object_type == "whatsapp_business_account"
    assert event.payload == json.loads(body)
    assert event.attempts == 0
    assert len(callbacks) == 1


@pytest.mark.parametrize(
    "signature",
    [
        None,
        "",
        "sha256=" + "0" * 64,
        sign(b"a different body"),
        sign(payload_bytes("text_message.json")).replace("sha256=", "sha1="),
        sign(payload_bytes("text_message.json"))[7:],
        "sha256=not-hex",
        sign(payload_bytes("text_message.json"), secret="another-app-secret"),
    ],
    ids=[
        "missing",
        "empty",
        "zeros",
        "other-body",
        "wrong-prefix",
        "no-prefix",
        "malformed",
        "other-secret",
    ],
)
def test_bad_signature_is_rejected_and_nothing_stored(client, signature):
    body = payload_bytes("text_message.json")

    with mock.patch.object(process_event, "delay") as delay:
        response = post_webhook(client, body, signature, signed=signature is not None)

    assert response.status_code == 401
    assert not WebhookEvent.objects.exists()
    delay.assert_not_called()


def test_post_rejected_when_app_secret_not_configured(client, settings):
    settings.META_APP_SECRET = ""
    body = payload_bytes("text_message.json")

    response = post_webhook(client, body, sign(body, secret=""))

    assert response.status_code == 401
    assert not WebhookEvent.objects.exists()


@pytest.mark.parametrize("body", [b"{not json", b"[1, 2, 3]", b"\xff\xfe"])
def test_invalid_json_is_rejected(client, body):
    response = post_webhook(client, body)

    assert response.status_code == 400
    assert not WebhookEvent.objects.exists()


def test_duplicate_body_stores_one_row_and_enqueues_once(
    client, django_capture_on_commit_callbacks
):
    body = payload_bytes("status_read.json")

    with (
        mock.patch.object(process_event, "delay") as delay,
        django_capture_on_commit_callbacks(execute=True),
    ):
        first = post_webhook(client, body)
        second = post_webhook(client, body)

    assert (first.status_code, second.status_code) == (200, 200)
    event = WebhookEvent.objects.get()
    delay.assert_called_once_with(str(event.pk))


def test_enqueue_failure_still_returns_200(client, django_capture_on_commit_callbacks):
    body = payload_bytes("text_message.json")

    with (
        mock.patch.object(process_event, "delay", side_effect=ConnectionError("broker down")),
        django_capture_on_commit_callbacks(execute=True),
    ):
        response = post_webhook(client, body)

    assert response.status_code == 200
    assert WebhookEvent.objects.get().status == WebhookEvent.Status.RECEIVED


def test_other_methods_not_allowed(client):
    assert client.put(callback_url(), data=b"{}").status_code == 405


# --- End to end -----------------------------------------------------------------------------


def test_signed_post_delivers_events_to_receivers(
    client, recorder, connected_number, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = post_webhook(client, payload_bytes("text_message.json"))

    assert response.status_code == 200
    event = WebhookEvent.objects.get()
    assert event.status == WebhookEvent.Status.PROCESSED
    assert event.workspace_id == connected_number.workspace_id
    assert event.processed_at is not None
    [message] = recorder.events
    assert isinstance(message, events.InboundMessage)
    assert message.workspace_id == connected_number.workspace_id
    assert message.webhook_event_id == event.pk
    assert message.text == "Hi, is the Diwali offer still available?"


def test_number_of_workspace_a_routes_to_a_not_b(
    client,
    recorder,
    workspace,
    other_workspace,
    connected_number,
    other_number,
    django_capture_on_commit_callbacks,
):
    with django_capture_on_commit_callbacks(execute=True):
        post_webhook(client, payload_bytes("status_delivered.json"))

    [status] = recorder.events
    assert isinstance(status, events.MessageStatus)
    assert status.workspace_id == workspace.pk
    assert status.workspace_id != other_workspace.pk
    assert WebhookEvent.objects.get().workspace_id == workspace.pk
