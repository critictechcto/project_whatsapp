import pytest
from django.urls import reverse

from apps.contacts.factories import ContactFactory, TagFactory
from apps.contacts.models import ConsentEvent, Contact
from common.roles import Role
from common.testing import assert_tenant_isolated, result_ids

pytestmark = pytest.mark.django_db

CONTACTS = reverse("contacts:contact-list")
BULK_TAG = reverse("contacts:contact-bulk-tag")


def contact_url(contact):
    return reverse("contacts:contact-detail", args=[contact.pk])


def action_url(contact, name):
    return reverse(f"contacts:contact-{name}", args=[contact.pk])


# --- Phone normalization -------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["9876543210", "098765 43210", "+91 98765 43210", "+919876543210", "919876543210"],
)
def test_create_normalizes_phone_to_e164(auth_client, workspace, raw):
    response = auth_client(Role.AGENT).post(CONTACTS, {"phone_e164": raw, "name": "Asha"})

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["phone_e164"] == "+919876543210"
    assert body["wa_id"] == "919876543210"
    assert Contact.objects.get(pk=body["id"]).workspace == workspace


@pytest.mark.parametrize("raw", ["12345", "not a number", ""])
def test_create_rejects_invalid_phone(auth_client, raw):
    response = auth_client().post(CONTACTS, {"phone_e164": raw})

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid"
    assert "phone_e164" in error["details"]


def test_duplicate_phone_in_workspace_is_conflict(auth_client, workspace):
    ContactFactory(workspace=workspace, phone_e164="+919876543210")

    response = auth_client().post(CONTACTS, {"phone_e164": "98765 43210"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_same_phone_allowed_in_another_workspace(auth_client, other_workspace):
    ContactFactory(workspace=other_workspace, phone_e164="+919876543210")

    response = auth_client().post(CONTACTS, {"phone_e164": "9876543210"})

    assert response.status_code == 201, response.content


def test_update_to_duplicate_phone_is_conflict(auth_client, workspace):
    ContactFactory(workspace=workspace, phone_e164="+919876543210")
    other = ContactFactory(workspace=workspace, phone_e164="+919876543211")

    response = auth_client().patch(contact_url(other), {"phone_e164": "+91 98765 43210"})

    assert response.status_code == 409


def test_consent_fields_are_read_only(auth_client):
    response = auth_client().post(
        CONTACTS,
        {
            "phone_e164": "9876543210",
            "marketing_opt_in_status": "opted_in",
            "opted_in_at": "2026-01-01T00:00:00Z",
            "attributes": {"city": "Pune"},
        },
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["marketing_opt_in_status"] == "unknown"
    assert body["opted_in_at"] is None
    assert body["attributes"] == {"city": "Pune"}


# --- Tags on contacts ----------------------------------------------------------------------


def test_tags_writable_as_workspace_ids(auth_client, workspace):
    tag = TagFactory(workspace=workspace)

    response = auth_client().post(CONTACTS, {"phone_e164": "9876543210", "tags": [str(tag.pk)]})

    assert response.status_code == 201, response.content
    assert response.json()["tags"] == [str(tag.pk)]


def test_foreign_workspace_tag_rejected(auth_client, other_workspace):
    foreign = TagFactory(workspace=other_workspace)

    response = auth_client().post(CONTACTS, {"phone_e164": "9876543210", "tags": [str(foreign.pk)]})

    assert response.status_code == 400
    assert "tags" in response.json()["error"]["details"]


# --- Listing ------------------------------------------------------------------------------


def test_filter_by_tag_status_and_search(auth_client, workspace):
    vip = TagFactory(workspace=workspace, name="vip")
    tagged = ContactFactory(workspace=workspace, name="Ravi Kumar", tags=[vip])
    opted_in = ContactFactory(
        workspace=workspace, name="Meera", marketing_opt_in_status=Contact.OptInStatus.OPTED_IN
    )
    client = auth_client(Role.VIEWER)

    assert result_ids(client.get(CONTACTS, {"tag": str(vip.pk)})) == {str(tagged.pk)}
    assert result_ids(client.get(CONTACTS, {"marketing_opt_in_status": "opted_in"})) == {
        str(opted_in.pk)
    }
    assert result_ids(client.get(CONTACTS, {"search": "ravi"})) == {str(tagged.pk)}
    search_phone = tagged.phone_e164[-6:]
    assert str(tagged.pk) in result_ids(client.get(CONTACTS, {"search": search_phone}))


def test_contacts_are_tenant_isolated(auth_client, other_workspace):
    foreign = ContactFactory(workspace=other_workspace)

    assert_tenant_isolated(
        auth_client(), object_id=foreign.pk, list_url=CONTACTS, detail_url=contact_url(foreign)
    )
    response = auth_client().get(action_url(foreign, "consent-events"))
    assert response.status_code == 404


# --- Roles --------------------------------------------------------------------------------


def test_viewer_reads_but_cannot_write(auth_client, workspace):
    contact = ContactFactory(workspace=workspace)
    client = auth_client(Role.VIEWER)

    assert client.get(CONTACTS).status_code == 200
    assert client.get(contact_url(contact)).status_code == 200
    response = client.post(CONTACTS, {"phone_e164": "9876543210"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_role"
    assert client.patch(contact_url(contact), {"name": "x"}).status_code == 403


def test_agent_writes_but_cannot_delete(auth_client, workspace):
    contact = ContactFactory(workspace=workspace)
    client = auth_client(Role.AGENT)

    assert client.patch(contact_url(contact), {"name": "New name"}).status_code == 200
    assert client.delete(contact_url(contact)).status_code == 403
    assert Contact.objects.filter(pk=contact.pk).exists()


def test_admin_deletes_contact(auth_client, workspace):
    contact = ContactFactory(workspace=workspace)

    assert auth_client(Role.ADMIN).delete(contact_url(contact)).status_code == 204
    assert not Contact.objects.filter(pk=contact.pk).exists()


# --- Consent endpoints --------------------------------------------------------------------


def test_opt_in_requires_evidence(auth_client, workspace):
    contact = ContactFactory(workspace=workspace)

    response = auth_client(Role.AGENT).post(action_url(contact, "opt-in"), {"source": "manual"})

    assert response.status_code == 400
    assert "evidence" in response.json()["error"]["details"]
    assert not ConsentEvent.objects.exists()


def test_opt_in_rejects_system_sources(auth_client, workspace):
    contact = ContactFactory(workspace=workspace)

    response = auth_client().post(
        action_url(contact, "opt-in"), {"source": "import", "evidence": "trust me"}
    )

    assert response.status_code == 400


def test_opt_in_and_out_write_consent_events(auth_client, workspace):
    contact = ContactFactory(workspace=workspace)
    agent = auth_client(Role.AGENT)

    response = agent.post(
        action_url(contact, "opt-in"),
        {"source": "manual", "evidence": "Signed the in-store form on 3 Sep"},
    )
    assert response.status_code == 200, response.content
    assert response.json()["marketing_opt_in_status"] == "opted_in"
    assert response.json()["opt_in_source"] == "manual"

    # Same state again: no new event.
    agent.post(action_url(contact, "opt-in"), {"source": "api", "evidence": "again"})

    response = agent.post(action_url(contact, "opt-out"), {})
    assert response.status_code == 200, response.content
    assert response.json()["marketing_opt_in_status"] == "opted_out"
    assert response.json()["opted_out_at"] is not None

    events = list(ConsentEvent.objects.filter(contact=contact).order_by("created_at"))
    assert [e.action for e in events] == ["opt_in", "opt_out"]
    assert events[0].evidence == "Signed the in-store form on 3 Sep"
    assert events[0].actor is not None
    assert events[0].workspace_id == workspace.pk

    response = auth_client(Role.VIEWER).get(action_url(contact, "consent-events"))
    assert response.status_code == 200
    assert result_ids(response) == {str(e.pk) for e in events}


def test_viewer_cannot_change_consent(auth_client, workspace):
    contact = ContactFactory(workspace=workspace)
    client = auth_client(Role.VIEWER)

    assert client.post(action_url(contact, "opt-out"), {}).status_code == 403
    assert client.post(action_url(contact, "opt-in"), {"evidence": "x"}).status_code == 403


# --- Bulk tag -----------------------------------------------------------------------------


def test_bulk_tag_adds_and_removes(auth_client, workspace):
    keep, drop = TagFactory(workspace=workspace), TagFactory(workspace=workspace)
    first = ContactFactory(workspace=workspace, tags=[drop])
    second = ContactFactory(workspace=workspace, tags=[keep])

    response = auth_client(Role.AGENT).post(
        BULK_TAG,
        {
            "contact_ids": [str(first.pk), str(second.pk)],
            "add_tag_ids": [str(keep.pk)],
            "remove_tag_ids": [str(drop.pk)],
        },
    )

    assert response.status_code == 200, response.content
    assert response.json() == {"contact_count": 2, "added": 1, "removed": 1}
    assert set(first.tags.all()) == {keep}
    assert set(second.tags.all()) == {keep}


def test_bulk_tag_rejects_foreign_ids(auth_client, workspace, other_workspace):
    mine = ContactFactory(workspace=workspace)
    tag = TagFactory(workspace=workspace)
    foreign_contact = ContactFactory(workspace=other_workspace)
    foreign_tag = TagFactory(workspace=other_workspace)
    client = auth_client()

    response = client.post(
        BULK_TAG,
        {"contact_ids": [str(mine.pk), str(foreign_contact.pk)], "add_tag_ids": [str(tag.pk)]},
    )
    assert response.status_code == 400
    assert "contact_ids" in response.json()["error"]["details"]

    response = client.post(
        BULK_TAG, {"contact_ids": [str(mine.pk)], "remove_tag_ids": [str(foreign_tag.pk)]}
    )
    assert response.status_code == 400
    assert "remove_tag_ids" in response.json()["error"]["details"]
    assert not mine.tags.exists()


def test_bulk_tag_requires_agent(auth_client, workspace):
    contact = ContactFactory(workspace=workspace)
    tag = TagFactory(workspace=workspace)

    response = auth_client(Role.VIEWER).post(
        BULK_TAG, {"contact_ids": [str(contact.pk)], "add_tag_ids": [str(tag.pk)]}
    )

    assert response.status_code == 403
