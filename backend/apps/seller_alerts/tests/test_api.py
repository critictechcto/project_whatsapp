"""Seller alerts API: platform info, recipients CRUD, verification, roles and tenant isolation."""

from datetime import timedelta

import pytest
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.seller_alerts.factories import AlertRecipientFactory
from apps.seller_alerts.models import AlertMessage, AlertRecipient
from apps.seller_alerts.schema_enums import ALERT_EVENTS, ALERT_RECIPIENT_STATUSES
from apps.whatsapp.client.errors import RecipientUnavailableError, TransientError
from common.roles import Role
from common.testing import assert_tenant_isolated, result_ids

pytestmark = pytest.mark.django_db

BASE = "/api/v1/seller-alerts"
PLATFORM = f"{BASE}/platform/"
RECIPIENTS = f"{BASE}/recipients/"


def error_code(response) -> str:
    return response.json()["error"]["code"]


def test_platform_info(auth_client, workspace):
    response = auth_client(Role.VIEWER).get(PLATFORM)

    assert response.status_code == 200, response.content
    assert response.json() == {"available": True, "display_phone_number": "+91 80000 00001"}


@pytest.mark.parametrize(
    "setting",
    [
        "PLATFORM_WA_ACCESS_TOKEN",
        "PLATFORM_WA_WABA_ID",
        "PLATFORM_WA_PHONE_NUMBER_ID",
        "PLATFORM_WA_DISPLAY_PHONE_NUMBER",
    ],
)
def test_platform_info_when_unconfigured(auth_client, workspace, settings, setting):
    setattr(settings, setting, "")

    response = auth_client(Role.VIEWER).get(PLATFORM)

    assert response.json() == {"available": False, "display_phone_number": ""}


def test_recipients_list(auth_client, workspace, other_workspace):
    recipient = AlertRecipientFactory(workspace=workspace, name="Ravi")
    AlertRecipientFactory(workspace=other_workspace)

    response = auth_client(Role.VIEWER).get(RECIPIENTS)

    assert response.status_code == 200, response.content
    [data] = response.json()["results"]
    assert data == {
        "id": str(recipient.pk),
        "name": "Ravi",
        "phone_e164": recipient.phone_e164,
        "status": "verified",
        "events": list(ALERT_EVENTS),
        "verified_at": data["verified_at"],
        "last_sent_at": None,
        "created_at": data["created_at"],
    }
    assert result_ids(response) == {str(recipient.pk)}


def test_recipients_are_tenant_isolated(auth_client, workspace, other_workspace, fake_graph):
    recipient = AlertRecipientFactory(workspace=workspace)
    client = auth_client(workspace=other_workspace)
    detail = f"{RECIPIENTS}{recipient.pk}/"

    assert_tenant_isolated(client, object_id=recipient.pk, list_url=RECIPIENTS)
    assert client.patch(detail, {"name": "X"}, format="json").status_code == 404
    assert client.delete(detail).status_code == 404
    assert client.post(f"{detail}resend-verification/").status_code == 404
    assert AlertRecipient.objects.filter(pk=recipient.pk, name=recipient.name).exists()
    assert fake_graph.sent_messages == []


@pytest.mark.parametrize(
    ("method", "suffix"),
    [("post", None), ("patch", ""), ("delete", ""), ("post", "resend-verification/")],
)
def test_recipient_writes_need_admin(auth_client, workspace, fake_graph, method, suffix):
    recipient = AlertRecipientFactory(workspace=workspace)
    url = RECIPIENTS if suffix is None else f"{RECIPIENTS}{recipient.pk}/{suffix}"

    denied = getattr(auth_client(Role.AGENT), method)(url, {}, format="json")

    assert denied.status_code == 403, denied.content


def test_create_sends_the_verification_template(auth_client, workspace, store, fake_graph):
    response = auth_client(Role.ADMIN).post(
        RECIPIENTS, {"name": "Ravi", "phone_e164": "98765 43210"}, format="json"
    )

    assert response.status_code == 201, response.content
    recipient = AlertRecipient.objects.get(workspace=workspace)
    assert response.json() == {
        "id": str(recipient.pk),
        "name": "Ravi",
        "phone_e164": "+919876543210",
        "status": "pending",
        "events": list(ALERT_EVENTS),
        "verified_at": None,
        "last_sent_at": response.json()["last_sent_at"],
        "created_at": response.json()["created_at"],
    }
    assert recipient.wa_id == "919876543210"
    assert recipient.verification_sent_at is not None
    assert recipient.last_sent_at is not None

    [sent] = fake_graph.sent_messages
    assert sent["phone_number_id"] == settings.PLATFORM_WA_PHONE_NUMBER_ID
    assert fake_graph.calls_to("send_message")[0].access_token == settings.PLATFORM_WA_ACCESS_TOKEN
    assert sent["to"] == "919876543210"
    assert sent["type"] == "template"
    assert sent["template"] == {
        "name": "upc_seller_verify",
        "language": {"code": "en"},
        "components": [
            {"type": "body", "parameters": [{"type": "text", "text": "Sharma Sweets"}]},
            {
                "type": "button",
                "sub_type": "quick_reply",
                "index": "0",
                "parameters": [{"type": "payload", "payload": f"upc:alerts:verify:{recipient.pk}"}],
            },
        ],
    }
    message = AlertMessage.objects.get()
    assert message.kind == AlertMessage.Kind.VERIFY
    assert message.status == AlertMessage.Status.SENT
    assert message.wamid == sent["wamid"]
    assert message.recipient == recipient
    assert message.workspace == workspace


def test_create_with_chosen_events(auth_client, workspace, store, fake_graph):
    response = auth_client(Role.ADMIN).post(
        RECIPIENTS,
        {
            "name": "Ravi",
            "phone_e164": "+919876543210",
            "events": ["order_cancelled", "new_order", "new_order"],
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    assert response.json()["events"] == ["new_order", "order_cancelled"]


def test_create_is_limited_to_three(auth_client, workspace, other_workspace, fake_graph):
    AlertRecipientFactory.create_batch(3, workspace=workspace)
    AlertRecipientFactory(workspace=other_workspace)

    response = auth_client(Role.ADMIN).post(
        RECIPIENTS, {"name": "Ravi", "phone_e164": "+919876543210"}, format="json"
    )

    assert response.status_code == 409, response.content
    assert error_code(response) == "alert_recipient_limit"
    assert fake_graph.sent_messages == []


@pytest.mark.parametrize("setting", ["PLATFORM_WA_ACCESS_TOKEN", "PLATFORM_WA_WABA_ID"])
def test_create_when_platform_unavailable(auth_client, workspace, settings, fake_graph, setting):
    setattr(settings, setting, "")

    response = auth_client(Role.ADMIN).post(
        RECIPIENTS, {"name": "Ravi", "phone_e164": "+919876543210"}, format="json"
    )

    assert response.status_code == 409, response.content
    assert error_code(response) == "platform_alerts_unavailable"
    assert not AlertRecipient.objects.exists()


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"name": "Ravi", "phone_e164": "12345"}, "phone_e164"),
        ({"name": "Ravi", "phone_e164": "+919700000001"}, "phone_e164"),  # already added
        ({"phone_e164": "+919876543210"}, "name"),
        ({"name": "Ravi", "phone_e164": "+919876543210", "events": ["sale"]}, "events"),
    ],
)
def test_create_validation(auth_client, workspace, store, fake_graph, body, field):
    AlertRecipientFactory(workspace=workspace, phone_e164="+919700000001")

    response = auth_client(Role.ADMIN).post(RECIPIENTS, body, format="json")

    assert response.status_code == 400, response.content
    assert field in response.json()["error"]["details"]
    assert fake_graph.sent_messages == []


def test_create_rejects_a_number_whatsapp_cannot_reach(auth_client, workspace, store, fake_graph):
    fake_graph.fail("send_message", RecipientUnavailableError("Message undeliverable", code=131026))

    response = auth_client(Role.ADMIN).post(
        RECIPIENTS, {"name": "Ravi", "phone_e164": "+919876543210"}, format="json"
    )

    assert response.status_code == 400, response.content
    assert "phone_e164" in response.json()["error"]["details"]
    assert not AlertRecipient.objects.exists()
    message = AlertMessage.objects.get()
    assert (message.status, message.error_code) == (AlertMessage.Status.FAILED, "131026")


def test_create_keeps_the_recipient_on_a_temporary_failure(
    auth_client, workspace, store, fake_graph
):
    fake_graph.fail("send_message", TransientError("Try later", code=131000))

    response = auth_client(Role.ADMIN).post(
        RECIPIENTS, {"name": "Ravi", "phone_e164": "+919876543210"}, format="json"
    )

    assert response.status_code == 201, response.content
    recipient = AlertRecipient.objects.get()
    assert recipient.verification_sent_at is None  # a resend is allowed right away
    resend = auth_client(Role.ADMIN).post(f"{RECIPIENTS}{recipient.pk}/resend-verification/")
    assert resend.status_code == 200, resend.content
    assert len(fake_graph.sent_messages) == 1


def test_patch_name_and_events(auth_client, workspace, fake_graph):
    recipient = AlertRecipientFactory(workspace=workspace, phone_e164="+919700000001")

    response = auth_client(Role.ADMIN).patch(
        f"{RECIPIENTS}{recipient.pk}/",
        {"name": "Asha", "events": ["needs_attention"], "phone_e164": "+91 97000 00001"},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert response.json()["name"] == "Asha"
    assert response.json()["events"] == ["needs_attention"]
    recipient.refresh_from_db()
    assert (recipient.name, recipient.events) == ("Asha", ["needs_attention"])
    assert fake_graph.sent_messages == []


def test_patch_cannot_change_the_phone(auth_client, workspace):
    recipient = AlertRecipientFactory(workspace=workspace, phone_e164="+919700000001")

    response = auth_client(Role.ADMIN).patch(
        f"{RECIPIENTS}{recipient.pk}/", {"phone_e164": "+919876543210"}, format="json"
    )

    assert response.status_code == 400, response.content
    assert "phone_e164" in response.json()["error"]["details"]


def test_delete(auth_client, workspace):
    recipient = AlertRecipientFactory(workspace=workspace)

    response = auth_client(Role.ADMIN).delete(f"{RECIPIENTS}{recipient.pk}/")

    assert response.status_code == 204, response.content
    assert not AlertRecipient.objects.exists()


def test_resend_verification_is_throttled(auth_client, workspace, store, fake_graph):
    recipient = AlertRecipientFactory(
        workspace=workspace,
        status=AlertRecipient.Status.PENDING,
        verified_at=None,
        verification_sent_at=timezone.now() - timedelta(minutes=6),
    )
    url = f"{RECIPIENTS}{recipient.pk}/resend-verification/"
    client = auth_client(Role.ADMIN)

    first = client.post(url)
    second = client.post(url)

    assert first.status_code == 200, first.content
    assert first.json()["status"] == "pending"
    assert second.status_code == 409, second.content
    assert error_code(second) == "verification_recently_sent"
    [sent] = fake_graph.sent_messages
    assert sent["template"]["name"] == "upc_seller_verify"


def test_resend_verification_when_platform_unavailable(auth_client, workspace, settings):
    recipient = AlertRecipientFactory(workspace=workspace)
    settings.PLATFORM_WA_ACCESS_TOKEN = ""

    response = auth_client(Role.ADMIN).post(f"{RECIPIENTS}{recipient.pk}/resend-verification/")

    assert response.status_code == 409, response.content
    assert error_code(response) == "platform_alerts_unavailable"


def test_phone_is_unique_per_workspace(workspace, other_workspace):
    AlertRecipientFactory(workspace=workspace, phone_e164="+919700000001")
    AlertRecipientFactory(workspace=other_workspace, phone_e164="+919700000001")

    with pytest.raises(IntegrityError), transaction.atomic():
        AlertRecipientFactory(workspace=workspace, phone_e164="+919700000001")


def test_model_choices_match_contract_enums():
    assert tuple(AlertRecipient.Status.values) == ALERT_RECIPIENT_STATUSES
