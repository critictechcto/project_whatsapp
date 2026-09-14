import uuid

import pytest

from apps.message_templates import tasks
from apps.message_templates.models import MessageTemplate
from apps.message_templates.schedules import BEAT_SCHEDULE
from apps.whatsapp.client.errors import TokenInvalidError, TransientError
from apps.whatsapp.factories import WhatsAppBusinessAccountFactory
from apps.whatsapp.models import WhatsAppBusinessAccount

pytestmark = pytest.mark.django_db


def test_sync_waba_task(waba, fake_graph):
    fake_graph.add_template(waba.waba_id, id="11", name="welcome")

    result = tasks.sync_waba.delay(str(waba.pk)).get()

    assert result == {"created": 1, "updated": 0, "deleted": 0}
    assert MessageTemplate.objects.filter(waba=waba).count() == 1


def test_sync_waba_retries_retryable_errors(waba, fake_graph):
    fake_graph.add_template(waba.waba_id, id="12", name="welcome")
    fake_graph.fail("list_templates", TransientError("Temporarily unavailable", code=2))

    # With eager propagation Celery re-raises Retry; throw=False lets apply() run the retry.
    result = tasks.sync_waba.apply(args=[str(waba.pk)], throw=False).get()

    assert result["created"] == 1
    assert len(fake_graph.calls_to("list_templates")) == 2


def test_sync_waba_gives_up_on_permanent_errors(waba, fake_graph):
    fake_graph.fail("list_templates", TokenInvalidError("Token expired", code=190))

    assert tasks.sync_waba.delay(str(waba.pk)).get() is None
    assert len(fake_graph.calls_to("list_templates")) == 1


def test_sync_waba_ignores_missing_waba(fake_graph):
    assert tasks.sync_waba.delay(str(uuid.uuid4())).get() is None
    assert fake_graph.calls == []


def test_sync_all_queues_connected_wabas(waba, fake_graph):
    WhatsAppBusinessAccountFactory(status=WhatsAppBusinessAccount.Status.DISABLED)
    WhatsAppBusinessAccountFactory(status=WhatsAppBusinessAccount.Status.DISCONNECTED)
    restricted = WhatsAppBusinessAccountFactory(status=WhatsAppBusinessAccount.Status.RESTRICTED)

    assert tasks.sync_all.delay().get() == 2

    synced = {call.kwargs["waba_id"] for call in fake_graph.calls_to("list_templates")}
    assert synced == {waba.waba_id, restricted.waba_id}


@pytest.mark.parametrize(
    "fields",
    [
        {"status": WhatsAppBusinessAccount.Status.PENDING},
        {"status": WhatsAppBusinessAccount.Status.DISCONNECTED},
        {"access_token": ""},
    ],
)
def test_sync_waba_skips_unconnected_accounts(fake_graph, fields):
    waba = WhatsAppBusinessAccountFactory(**fields)

    assert tasks.sync_waba.delay(str(waba.pk)).get() is None
    assert fake_graph.calls == []


def test_beat_schedule_entry():
    entry = BEAT_SCHEDULE["message_templates.sync_all"]
    assert entry["task"] == tasks.sync_all.name
    assert all(name.startswith("message_templates.") for name in BEAT_SCHEDULE)
