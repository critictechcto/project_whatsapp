"""Reports run a fixed number of aggregate queries, however much data there is."""

import pytest
from django.core.cache import cache

from apps.automations.factories import AutomationRunFactory
from apps.billing import services
from apps.campaigns.factories import CampaignFactory
from apps.contacts.factories import ContactFactory
from apps.inbox.factories import ConversationFactory
from apps.message_templates.factories import MessageTemplateFactory
from apps.orders.factories import OrderFactory, OrderItemFactory
from apps.tenants.factories import MembershipFactory
from common.roles import Role

from .helpers import REPORTS, backdate, local, message, url

pytestmark = pytest.mark.django_db

# User, membership and subscription lookups, then the aggregates (overview has 6).
MAX_QUERIES = 9


def seed(workspace, conversation, size: int) -> None:
    services.get_subscription(workspace)  # exists in real workspaces; creating it costs queries
    template = MessageTemplateFactory(waba=conversation.phone_number.waba, name="welcome")
    for index in range(size):
        member = MembershipFactory(workspace=workspace, role=Role.AGENT).user
        other = ConversationFactory(workspace=workspace, assignee=member)
        backdate(other, local("2026-03-10 10:00"), "last_message_at")
        message(conversation, "2026-03-10 10:00", sent_by=member, status="read")
        message(
            conversation,
            "2026-03-11 10:00",
            source="campaign",
            type="template",
            template=template,
            template_name=f"template_{index}",
            template_language="en",
            template_category="marketing",
            status="failed",
            error_code=str(131000 + index),
        )
        message(conversation, "2026-03-12 10:00", inbound=True)
        backdate(ContactFactory(workspace=workspace), local("2026-03-10 10:00"))
        campaign = CampaignFactory(phone_number=conversation.phone_number)
        backdate(campaign, local("2026-03-10 10:00"), "started_at")
        AutomationRunFactory(message__conversation=conversation)
        order = OrderFactory(workspace=workspace)
        backdate(order, local("2026-03-11 10:00"))
        OrderItemFactory(order=order)


@pytest.mark.parametrize("size", [1, 4])
@pytest.mark.parametrize("report", REPORTS)
def test_query_count_is_bounded(
    client, workspace, conversation, django_assert_max_num_queries, report, size
):
    seed(workspace, conversation, size)
    cache.clear()

    with django_assert_max_num_queries(MAX_QUERIES):
        response = client.get(url(report, **{"from": "2026-03-01", "to": "2026-03-15"}))

    assert response.status_code == 200


def test_export_query_count_is_bounded(
    client, workspace, conversation, django_assert_max_num_queries
):
    seed(workspace, conversation, 3)

    with django_assert_max_num_queries(MAX_QUERIES):
        response = client.get(url("export", report="team"))

    assert response.status_code == 200
