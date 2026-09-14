import pytest
from django.urls import reverse

from apps.webhooks.factories import WebhookEventFactory
from apps.webhooks.models import WebhookEvent
from apps.webhooks.schedules import BEAT_SCHEDULE

from .helpers import load_payload

pytestmark = pytest.mark.django_db

CHANGELIST = "admin:webhooks_webhookevent_changelist"


def test_changelist_and_detail_render(admin_client):
    event = WebhookEventFactory(payload=load_payload("template_approved.json"))

    assert admin_client.get(reverse(CHANGELIST), {"status__exact": "received"}).status_code == 200
    response = admin_client.get(reverse("admin:webhooks_webhookevent_change", args=[event.pk]))
    assert response.status_code == 200
    assert b"diwali_offer_2026" in response.content


def test_reprocess_selected(
    admin_client, recorder, connected_number, django_capture_on_commit_callbacks
):
    failed = WebhookEventFactory(
        payload=load_payload("text_message.json"), status=WebhookEvent.Status.FAILED, attempts=6
    )
    processing = WebhookEventFactory(status=WebhookEvent.Status.PROCESSING, attempts=1)

    with django_capture_on_commit_callbacks(execute=True):
        response = admin_client.post(
            reverse(CHANGELIST),
            {"action": "reprocess_selected", "_selected_action": [failed.pk, processing.pk]},
        )

    assert response.status_code == 302
    failed.refresh_from_db()
    processing.refresh_from_db()
    assert failed.status == WebhookEvent.Status.PROCESSED
    assert failed.attempts == 7
    assert processing.status == WebhookEvent.Status.PROCESSING
    assert len(recorder.events) == 1


def test_beat_schedule_entries():
    assert set(BEAT_SCHEDULE) == {"webhooks.requeue_stuck_events", "webhooks.purge_old_events"}
    for name, entry in BEAT_SCHEDULE.items():
        assert entry["task"] == name
