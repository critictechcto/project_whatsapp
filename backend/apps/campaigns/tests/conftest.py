import pytest

from apps.campaigns import services
from apps.campaigns.factories import CampaignFactory
from apps.campaigns.models import CampaignRecipient
from apps.campaigns.tasks import send_batch
from apps.contacts.factories import ContactFactory, TagFactory
from apps.contacts.models import Contact
from apps.message_templates.factories import MessageTemplateFactory
from apps.message_templates.models import MessageTemplate
from apps.whatsapp.factories import PhoneNumberFactory
from common import events

BASE = "/api/v1/campaigns"

MAPPING = {
    "body": [
        {"source": "contact_field", "value": "name", "fallback": "there"},
        {"source": "static", "value": "ORD-1001", "fallback": ""},
    ],
    "header": None,
    "buttons": {},
}


def tag_audience(*tags, match="any") -> dict:
    return {"tag_ids": [str(tag.pk) for tag in tags], "match": match, "contact_ids": []}


@pytest.fixture
def commit(django_capture_on_commit_callbacks):
    """``with commit():`` runs on_commit callbacks (batches, dispatch, events) on exit."""
    return lambda: django_capture_on_commit_callbacks(execute=True)


@pytest.fixture
def emit():
    def _emit(signal, event) -> None:
        failures = events.emit(signal, event)
        assert not failures, failures

    return _emit


@pytest.fixture
def number(workspace):
    """The workspace's default, registered number on a connected WABA."""
    return PhoneNumberFactory(workspace=workspace, waba__workspace=workspace, is_default=True)


@pytest.fixture
def template(number):
    """Approved MARKETING template: ``Hi {{1}}, your order {{2}} has shipped.``"""
    return MessageTemplateFactory(
        waba=number.waba,
        status=MessageTemplate.Status.APPROVED,
        category=MessageTemplate.Category.MARKETING,
    )


@pytest.fixture
def tag(workspace):
    return TagFactory(workspace=workspace)


@pytest.fixture
def make_contact(workspace, tag):
    """Opted-in contact with ``tag`` unless told otherwise."""

    def make(status=Contact.OptInStatus.OPTED_IN, *, tagged=True, **fields):
        return ContactFactory(
            workspace=workspace,
            marketing_opt_in_status=status,
            tags=[tag] if tagged else None,
            **fields,
        )

    return make


@pytest.fixture
def launched(number, template, tag, make_contact):
    """``launched(count)`` -> (running campaign, contacts); no batch has run yet."""

    def make(count=1, *, scheduled_at=services.UNSET, **fields):
        contacts = [make_contact() for _ in range(count)]
        campaign = CampaignFactory(
            phone_number=number, template=template, audience=tag_audience(tag), **fields
        )
        services.launch(campaign, actor=None, scheduled_at=scheduled_at)
        campaign.refresh_from_db()
        return campaign, contacts

    return make


@pytest.fixture
def queued(launched):
    """``queued(count)`` -> (running campaign, recipients) with one queued message each."""

    def make(count=1):
        campaign, _ = launched(count)
        send_batch.apply(args=[str(campaign.pk)])
        recipients = list(
            CampaignRecipient.objects.filter(campaign=campaign)
            .select_related("message")
            .order_by("created_at", "pk")
        )
        assert [r.status for r in recipients] == ["queued"] * count
        campaign.refresh_from_db()
        return campaign, recipients

    return make
