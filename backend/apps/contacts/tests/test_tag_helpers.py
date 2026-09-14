import pytest

from apps.contacts import services
from apps.contacts.factories import ContactFactory, TagFactory

pytestmark = pytest.mark.django_db


def test_add_and_remove_tags_are_idempotent(workspace):
    contact = ContactFactory(workspace=workspace)
    vip, lead = TagFactory(workspace=workspace), TagFactory(workspace=workspace)

    services.add_tags(contact, [vip, lead])
    services.add_tags(contact, [vip])
    assert set(contact.tags.all()) == {vip, lead}

    services.remove_tags(contact, [lead])
    services.remove_tags(contact, [lead])
    assert list(contact.tags.all()) == [vip]


def test_tags_from_another_workspace_are_rejected(workspace, other_workspace):
    contact = ContactFactory(workspace=workspace)

    with pytest.raises(ValueError):
        services.add_tags(contact, [TagFactory(workspace=other_workspace)])
    assert not contact.tags.exists()
