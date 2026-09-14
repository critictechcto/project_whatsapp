import pytest

from apps.campaigns import demo
from apps.campaigns.models import Campaign, CampaignRecipient
from apps.contacts.models import Contact
from apps.message_templates.models import MessageTemplate
from apps.whatsapp.factories import PhoneNumberFactory

pytestmark = pytest.mark.django_db


def test_seed_is_idempotent_and_offline(workspace, fake_graph):
    PhoneNumberFactory(workspace=workspace, waba__workspace=workspace, is_default=True)

    demo.seed(workspace)
    demo.seed(workspace)

    campaigns = Campaign.objects.filter(workspace=workspace)
    assert sorted(campaigns.values_list("status", flat=True)) == ["completed", "draft"]
    completed = campaigns.get(name=demo.COMPLETED_NAME)
    assert completed.stats == {
        "total": 12,
        "skipped": 1,
        "queued": 0,
        "sent": 10,
        "delivered": 9,
        "read": 6,
        "failed": 1,
        "replied": 3,
    }
    assert CampaignRecipient.objects.filter(campaign=completed).count() == 12
    assert MessageTemplate.objects.filter(workspace=workspace).count() == 1
    assert Contact.objects.filter(workspace=workspace).count() == 12
    assert fake_graph.calls == []


def test_seed_without_a_number_does_nothing(workspace):
    demo.seed(workspace)

    assert not Campaign.objects.filter(workspace=workspace).exists()
