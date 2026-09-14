"""Seller alerts API: platform info, recipient list, role-gated stubs and tenant isolation."""

import pytest
from django.db import IntegrityError, transaction

from apps.seller_alerts.factories import AlertRecipientFactory
from apps.seller_alerts.models import AlertRecipient
from apps.seller_alerts.schema_enums import ALERT_EVENTS, ALERT_RECIPIENT_STATUSES
from common.roles import Role
from common.testing import assert_tenant_isolated, result_ids

pytestmark = pytest.mark.django_db

BASE = "/api/v1/seller-alerts"
PLATFORM = f"{BASE}/platform/"
RECIPIENTS = f"{BASE}/recipients/"


def test_platform_info(auth_client, workspace):
    response = auth_client(Role.VIEWER).get(PLATFORM)

    assert response.status_code == 200, response.content
    assert response.json() == {"available": True, "display_phone_number": "+91 80000 00001"}


def test_platform_info_when_unconfigured(auth_client, workspace, settings):
    settings.PLATFORM_WA_ACCESS_TOKEN = ""

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


def test_recipients_are_tenant_isolated(auth_client, workspace, other_workspace):
    recipient = AlertRecipientFactory(workspace=workspace)
    client = auth_client(workspace=other_workspace)

    assert_tenant_isolated(client, object_id=recipient.pk, list_url=RECIPIENTS)
    response = client.patch(f"{RECIPIENTS}{recipient.pk}/", {}, format="json")
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("post", None),
        ("patch", ""),
        ("delete", ""),
        ("post", "resend-verification/"),
    ],
)
def test_recipient_writes_are_admin_stubs(auth_client, workspace, method, suffix):
    recipient = AlertRecipientFactory(workspace=workspace)
    url = RECIPIENTS if suffix is None else f"{RECIPIENTS}{recipient.pk}/{suffix}"

    denied = getattr(auth_client(Role.AGENT), method)(url, {}, format="json")
    allowed = getattr(auth_client(Role.ADMIN), method)(url, {}, format="json")

    assert denied.status_code == 403, denied.content
    assert allowed.status_code == 501, allowed.content
    assert allowed.json()["error"]["code"] == "not_implemented"


def test_phone_is_unique_per_workspace(workspace, other_workspace):
    AlertRecipientFactory(workspace=workspace, phone_e164="+919700000001")
    AlertRecipientFactory(workspace=other_workspace, phone_e164="+919700000001")

    with pytest.raises(IntegrityError), transaction.atomic():
        AlertRecipientFactory(workspace=workspace, phone_e164="+919700000001")


def test_model_choices_match_contract_enums():
    assert tuple(AlertRecipient.Status.values) == ALERT_RECIPIENT_STATUSES
