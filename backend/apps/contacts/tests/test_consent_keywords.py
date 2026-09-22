"""Editable consent keywords: the settings API and how inbound messages use them."""

import pytest
from django.urls import reverse

from apps.contacts import services
from apps.contacts.models import ConsentKeywords, Contact
from common.events import emit, inbound_message_received
from common.roles import Role

from .test_receivers import WA_ID, inbound

pytestmark = pytest.mark.django_db

URL = reverse("contacts:consent-keywords")


def contact_status(workspace) -> str:
    return Contact.objects.get(workspace=workspace, wa_id=WA_ID).marketing_opt_in_status


# --- API ----------------------------------------------------------------------------------------


def test_defaults_are_returned_for_a_new_workspace(auth_client):
    response = auth_client(Role.VIEWER).get(URL)

    assert response.status_code == 200
    body = response.json()
    assert body["opt_in_keywords"] == ["start", "subscribe"]
    assert body["opt_out_keywords"] == []
    assert body["locked_opt_out_keywords"] == ["stop", "stop all", "stop promotions", "unsubscribe"]
    assert body["default_opt_in_keywords"] == ["start", "subscribe"]


def test_admins_save_normalised_words(auth_client, workspace):
    response = auth_client(Role.ADMIN).patch(
        URL,
        {
            "opt_in_keywords": ["  HAAN! ", "Offers", "offers", ""],
            "opt_out_keywords": ["Band   Karo", "STOP"],
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["opt_in_keywords"] == ["haan", "offers"]
    # STOP is already locked, so it isn't stored as an extra.
    assert body["opt_out_keywords"] == ["band karo"]
    stored = ConsentKeywords.objects.get(workspace=workspace)
    assert (stored.opt_in_keywords, stored.opt_out_keywords) == (["haan", "offers"], ["band karo"])


def test_partial_update_keeps_the_other_list(auth_client):
    client = auth_client(Role.ADMIN)
    client.patch(URL, {"opt_out_keywords": ["band karo"]}, format="json")

    body = client.patch(URL, {"opt_in_keywords": []}, format="json").json()

    assert body["opt_in_keywords"] == []
    assert body["opt_out_keywords"] == ["band karo"]


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"opt_in_keywords": ["stop"]}, "opt_in_keywords"),
        ({"opt_in_keywords": ["no more"], "opt_out_keywords": ["No more"]}, "opt_in_keywords"),
        ({"opt_in_keywords": ["x" * 41]}, "opt_in_keywords"),
        ({"opt_out_keywords": [f"word {i}" for i in range(21)]}, "opt_out_keywords"),
    ],
)
def test_invalid_words_are_rejected(auth_client, payload, field):
    response = auth_client(Role.ADMIN).patch(URL, payload, format="json")

    assert response.status_code == 400
    assert field in response.json()["error"]["details"]


def test_agents_cannot_edit(auth_client):
    response = auth_client(Role.AGENT).patch(URL, {"opt_in_keywords": []}, format="json")

    assert response.status_code == 403


def test_settings_are_per_workspace(auth_client, workspace, other_workspace):
    auth_client(Role.ADMIN).patch(URL, {"opt_in_keywords": ["haan"]}, format="json")

    other = auth_client(workspace=other_workspace).get(URL).json()

    assert other["opt_in_keywords"] == ["start", "subscribe"]


# --- Inbound messages ---------------------------------------------------------------------------


def test_custom_words_record_consent(workspace):
    ConsentKeywords.objects.create(
        workspace=workspace, opt_in_keywords=["haan"], opt_out_keywords=["band karo"]
    )

    emit(inbound_message_received, inbound(workspace.pk, text="Haan!"))
    assert contact_status(workspace) == "opted_in"

    emit(inbound_message_received, inbound(workspace.pk, text="BAND KARO"))
    assert contact_status(workspace) == "opted_out"


def test_removed_defaults_no_longer_opt_in_but_stop_always_works(workspace):
    ConsentKeywords.objects.create(workspace=workspace, opt_in_keywords=["haan"])

    emit(inbound_message_received, inbound(workspace.pk, text="START"))
    assert contact_status(workspace) == "unknown"

    emit(inbound_message_received, inbound(workspace.pk, text="haan"))
    emit(inbound_message_received, inbound(workspace.pk, text="stop"))
    assert contact_status(workspace) == "opted_out"


def test_long_messages_skip_the_keyword_lookup(workspace, django_assert_num_queries):
    with django_assert_num_queries(0):
        assert services.match_workspace_consent_keyword(workspace.pk, "x" * 41) is None
