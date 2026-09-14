import pytest
from django.urls import reverse

from apps.contacts.factories import ContactFactory, TagFactory
from apps.contacts.models import Tag
from common.roles import Role
from common.testing import assert_tenant_isolated, result_ids

pytestmark = pytest.mark.django_db

TAGS = reverse("contacts:tag-list")


def tag_url(tag):
    return reverse("contacts:tag-detail", args=[tag.pk])


def test_agent_creates_tag(auth_client, workspace):
    response = auth_client(Role.AGENT).post(TAGS, {"name": " VIP ", "color": "#25D366"})

    assert response.status_code == 201, response.content
    tag = Tag.objects.get(pk=response.json()["id"])
    assert (tag.workspace, tag.name, tag.color) == (workspace, "VIP", "#25D366")


def test_tag_name_unique_case_insensitive(auth_client, workspace):
    TagFactory(workspace=workspace, name="VIP")

    response = auth_client().post(TAGS, {"name": "vip"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_rename_to_existing_tag_is_conflict(auth_client, workspace):
    TagFactory(workspace=workspace, name="VIP")
    other = TagFactory(workspace=workspace, name="Leads")

    assert auth_client().patch(tag_url(other), {"name": "Vip"}).status_code == 409
    assert auth_client().patch(tag_url(other), {"name": "leads"}).status_code == 200


def test_same_tag_name_in_another_workspace(auth_client, other_workspace):
    TagFactory(workspace=other_workspace, name="VIP")

    assert auth_client().post(TAGS, {"name": "VIP"}).status_code == 201


def test_invalid_color_rejected(auth_client):
    response = auth_client().post(TAGS, {"name": "VIP", "color": "green"})

    assert response.status_code == 400
    assert "color" in response.json()["error"]["details"]


def test_viewer_lists_but_cannot_write_tags(auth_client, workspace):
    tag = TagFactory(workspace=workspace)
    client = auth_client(Role.VIEWER)

    response = client.get(TAGS)
    assert response.status_code == 200
    assert result_ids(response) == {str(tag.pk)}
    assert client.post(TAGS, {"name": "new"}).status_code == 403
    assert client.delete(tag_url(tag)).status_code == 403


def test_deleting_tag_untags_contacts(auth_client, workspace):
    tag = TagFactory(workspace=workspace)
    contact = ContactFactory(workspace=workspace, tags=[tag])

    assert auth_client(Role.AGENT).delete(tag_url(tag)).status_code == 204
    assert not contact.tags.exists()


def test_tags_are_tenant_isolated(auth_client, other_workspace):
    foreign = TagFactory(workspace=other_workspace)

    assert_tenant_isolated(
        auth_client(), object_id=foreign.pk, list_url=TAGS, detail_url=tag_url(foreign)
    )
