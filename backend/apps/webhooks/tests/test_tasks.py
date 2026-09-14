from datetime import timedelta
from unittest import mock

import pytest
from celery.exceptions import Retry
from django.utils import timezone

from apps.webhooks.factories import WebhookEventFactory
from apps.webhooks.models import WebhookEvent
from apps.webhooks.tasks import (
    MAX_RETRIES,
    WebhookProcessingError,
    process_event,
    purge_old_events,
    requeue_stuck_events,
)
from apps.whatsapp.factories import PhoneNumberFactory
from common import events

from .helpers import load_payload

pytestmark = pytest.mark.django_db

Status = WebhookEvent.Status


def make_event(name: str, **kwargs) -> WebhookEvent:
    return WebhookEventFactory(payload=load_payload(name), **kwargs)


def refreshed(event: WebhookEvent) -> WebhookEvent:
    event.refresh_from_db()
    return event


@pytest.fixture
def worker_like_retries():
    """Test settings propagate eager exceptions, which turns ``self.retry`` into a raise. Disable
    propagation so eager ``apply`` re-runs the task on Retry the way a worker would."""
    conf = process_event.app.conf
    previous = conf.task_eager_propagates
    # Settings come from Django under the CELERY_ namespace, which shadows the plain key.
    conf.CELERY_TASK_EAGER_PROPAGATES = False
    yield
    conf.CELERY_TASK_EAGER_PROPAGATES = previous


def backdate(event: WebhookEvent, **fields) -> None:
    WebhookEvent.objects.filter(pk=event.pk).update(**fields)


# --- process_event: routing -----------------------------------------------------------------


def test_routes_inbound_message_by_phone_number(recorder, connected_number):
    event = make_event("text_message.json")

    process_event.delay(str(event.pk))

    event = refreshed(event)
    assert event.status == Status.PROCESSED
    assert event.attempts == 1
    assert event.processed_at is not None
    assert event.workspace_id == connected_number.workspace_id
    assert event.last_error == ""
    [message] = recorder.of(events.InboundMessage)
    assert message.workspace_id == connected_number.workspace_id
    assert message.webhook_event_id == event.pk
    assert message.phone_number_id == connected_number.phone_number_id


def test_batched_delivery_routes_each_change_to_its_workspace(
    recorder, workspace, other_workspace, connected_number, other_number
):
    event = make_event("batched.json")

    process_event.delay(str(event.pk))

    event = refreshed(event)
    assert event.status == Status.PROCESSED
    assert event.workspace_id == workspace.pk  # first routed workspace
    assert len(recorder.events) == 5
    by_workspace = {(type(e).__name__, e.workspace_id) for e in recorder.events}
    assert by_workspace == {
        ("InboundMessage", workspace.pk),
        ("MessageStatus", workspace.pk),
        ("TemplateStatusUpdate", workspace.pk),
        ("MessageStatus", other_workspace.pk),
    }
    [other_status] = [e for e in recorder.events if e.workspace_id == other_workspace.pk]
    assert other_status.recipient_wa_id == "919999888777"


@pytest.mark.parametrize(
    ("name", "event_class"),
    [
        ("template_approved.json", events.TemplateStatusUpdate),
        ("template_rejected.json", events.TemplateStatusUpdate),
        ("template_category_update.json", events.TemplateCategoryUpdate),
        ("template_quality_update.json", events.TemplateQualityUpdate),
        ("phone_number_quality_downgrade.json", events.PhoneNumberQualityUpdate),
        ("account_update.json", events.AccountUpdate),
    ],
)
def test_waba_level_changes_route_by_waba_id(recorder, connected_number, name, event_class):
    event = make_event(name)

    process_event.delay(str(event.pk))

    assert refreshed(event).status == Status.PROCESSED
    [emitted] = recorder.events
    assert isinstance(emitted, event_class)
    assert emitted.workspace_id == connected_number.workspace_id
    assert emitted.waba_id == connected_number.waba.waba_id


def test_unknown_phone_number_falls_back_to_waba(recorder, connected_number):
    payload = load_payload("text_message.json")
    payload["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = "100000000000001"
    event = WebhookEventFactory(payload=payload)

    process_event.delay(str(event.pk))

    [message] = recorder.events
    assert message.workspace_id == connected_number.workspace_id
    assert message.phone_number_id == "100000000000001"


def test_unroutable_phone_number_marks_event_unroutable(recorder, connected_number):
    event = make_event("unroutable_phone_number.json")

    process_event.delay(str(event.pk))

    event = refreshed(event)
    assert event.status == Status.UNROUTABLE
    assert event.workspace_id is None
    assert recorder.events == []


def test_unknown_field_is_unroutable_not_failed(recorder, connected_number):
    event = make_event("unknown_field.json")

    process_event.delay(str(event.pk))

    assert refreshed(event).status == Status.UNROUTABLE
    assert recorder.events == []


# --- process_event: failures, retries, idempotency ------------------------------------------


def test_receiver_failure_marks_failed_and_schedules_retry(recorder, connected_number):
    def broken(sender, event, **kwargs):
        raise RuntimeError("boom")

    events.inbound_message_received.connect(broken, weak=False)
    event = make_event("text_message.json")

    with mock.patch("celery.app.task.Task.retry", side_effect=Retry()) as retry:
        result = process_event.apply(args=[str(event.pk)], throw=False)

    assert result.state == "RETRY"

    event = refreshed(event)
    assert event.status == Status.FAILED
    assert event.attempts == 1
    assert "boom" in event.last_error
    assert "broken" in event.last_error
    assert event.workspace_id == connected_number.workspace_id
    assert event.processed_at is None
    retry.assert_called_once()
    assert retry.call_args.kwargs["countdown"] == 60
    assert retry.call_args.kwargs["max_retries"] == MAX_RETRIES
    assert isinstance(retry.call_args.kwargs["exc"], WebhookProcessingError)


def test_retry_succeeds_once_receiver_recovers(recorder, connected_number, worker_like_retries):
    calls = []

    def flaky(sender, event, **kwargs):
        calls.append(event)
        if len(calls) == 1:
            raise RuntimeError("temporary")

    events.inbound_message_received.connect(flaky, weak=False)
    event = make_event("text_message.json")

    assert process_event.delay(str(event.pk)).state == "SUCCESS"

    event = refreshed(event)
    assert event.status == Status.PROCESSED
    assert event.attempts == 2
    assert event.last_error == ""
    assert len(calls) == 2
    assert len(recorder.events) == 2  # redelivered: receivers must be idempotent


def test_persistent_receiver_failure_gives_up_after_max_retries(
    recorder, connected_number, worker_like_retries
):
    def broken(sender, event, **kwargs):
        raise RuntimeError("still broken")

    events.message_status_updated.connect(broken, weak=False)
    event = make_event("status_sent.json")

    result = process_event.delay(str(event.pk))

    assert result.state == "FAILURE"
    assert isinstance(result.result, WebhookProcessingError)
    event = refreshed(event)
    assert event.status == Status.FAILED
    assert event.attempts == MAX_RETRIES + 1
    assert "still broken" in event.last_error


def test_processed_event_is_not_processed_again(recorder, connected_number):
    event = make_event("text_message.json")
    process_event.delay(str(event.pk))
    recorder.events.clear()

    process_event.delay(str(event.pk))

    event = refreshed(event)
    assert event.status == Status.PROCESSED
    assert event.attempts == 1
    assert recorder.events == []


@pytest.mark.parametrize("status", [Status.PROCESSING, Status.UNROUTABLE])
def test_rows_not_claimable_are_skipped(recorder, connected_number, status):
    event = make_event("text_message.json", status=status, attempts=1)

    process_event.delay(str(event.pk))

    assert refreshed(event).attempts == 1
    assert recorder.events == []


def test_missing_event_is_a_noop(recorder):
    assert process_event.delay("00000000-0000-0000-0000-000000000000").result is None


def test_parser_crash_marks_failed_without_retry(recorder, connected_number):
    event = make_event("text_message.json")

    with (
        mock.patch("apps.webhooks.tasks.parse_payload", side_effect=KeyError("bug")),
        mock.patch("celery.app.task.Task.retry") as retry,
    ):
        process_event.delay(str(event.pk))

    event = refreshed(event)
    assert event.status == Status.FAILED
    assert "Parse error" in event.last_error
    retry.assert_not_called()


# --- process_event: the platform alerts number ----------------------------------------------

PLATFORM_NUMBER_ID = "990000000000002"
PLATFORM_WABA_ID = "990000000000001"


def platform_payload(name: str) -> dict:
    payload = load_payload(name)
    for entry in payload["entry"]:
        entry["id"] = PLATFORM_WABA_ID
        for change in entry["changes"]:
            change["value"]["metadata"]["phone_number_id"] = PLATFORM_NUMBER_ID
    return payload


@pytest.fixture
def platform_number(settings):
    settings.PLATFORM_WA_PHONE_NUMBER_ID = PLATFORM_NUMBER_ID
    return PLATFORM_NUMBER_ID


def test_platform_number_messages_emit_platform_events(recorder, connected_number, platform_number):
    event = WebhookEventFactory(payload=platform_payload("interactive_button_reply.json"))

    process_event.delay(str(event.pk))

    event = refreshed(event)
    assert event.status == Status.PROCESSED
    assert event.workspace_id is None
    assert recorder.of(events.InboundMessage) == []
    [message] = recorder.of(events.PlatformInboundMessage)
    parsed = load_payload("interactive_button_reply.json")["entry"][0]["changes"][0]["value"]
    raw = parsed["messages"][0]
    assert message.phone_number_id == PLATFORM_NUMBER_ID
    assert message.wamid == raw["id"]
    assert message.from_wa_id == raw["from"]
    assert message.type == "interactive"
    assert message.text == "Confirm"
    assert message.reply_id == "confirm_booking"
    assert message.profile_name == parsed["contacts"][0]["profile"]["name"]
    assert message.context_wamid == raw["context"]["id"]
    assert message.payload == raw
    assert message.webhook_event_id == event.pk


def test_platform_number_is_routed_even_when_a_workspace_has_that_number(
    recorder, workspace, platform_number
):
    PhoneNumberFactory(
        workspace=workspace, waba__workspace=workspace, phone_number_id=PLATFORM_NUMBER_ID
    )
    event = WebhookEventFactory(payload=platform_payload("text_message.json"))

    process_event.delay(str(event.pk))

    assert refreshed(event).workspace_id is None
    assert recorder.of(events.InboundMessage) == []
    assert len(recorder.of(events.PlatformInboundMessage)) == 1


def test_platform_number_statuses_are_dropped(recorder, connected_number, platform_number, caplog):
    event = WebhookEventFactory(payload=platform_payload("status_failed.json"))

    with caplog.at_level("DEBUG", logger="apps.webhooks.tasks"):
        process_event.delay(str(event.pk))

    assert refreshed(event).status == Status.PROCESSED
    assert recorder.events == []
    assert "Dropping MessageStatus for the platform number" in caplog.text


def test_platform_and_workspace_changes_in_one_delivery(
    recorder, connected_number, platform_number
):
    payload = load_payload("text_message.json")
    platform_entry = platform_payload("text_message.json")["entry"][0]
    platform_entry["changes"][0]["value"]["messages"][0]["id"] = "wamid.PLATFORM"
    payload["entry"].append(platform_entry)
    event = WebhookEventFactory(payload=payload)

    process_event.delay(str(event.pk))

    event = refreshed(event)
    assert event.status == Status.PROCESSED
    assert event.workspace_id == connected_number.workspace_id
    [inbound] = recorder.of(events.InboundMessage)
    [platform] = recorder.of(events.PlatformInboundMessage)
    assert inbound.phone_number_id == connected_number.phone_number_id
    assert platform.wamid == "wamid.PLATFORM"


def test_platform_routing_is_off_without_the_setting(recorder, connected_number, settings):
    settings.PLATFORM_WA_PHONE_NUMBER_ID = ""
    payload = load_payload("text_message.json")
    payload["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = ""
    event = WebhookEventFactory(payload=payload)

    process_event.delay(str(event.pk))

    assert recorder.of(events.PlatformInboundMessage) == []
    [message] = recorder.of(events.InboundMessage)  # routed by WABA as before
    assert message.workspace_id == connected_number.workspace_id


def test_platform_receiver_failure_marks_failed_and_schedules_retry(recorder, platform_number):
    def broken(sender, event, **kwargs):
        raise RuntimeError("alerts down")

    events.platform_inbound_message_received.connect(broken, weak=False)
    event = WebhookEventFactory(payload=platform_payload("text_message.json"))

    with mock.patch("celery.app.task.Task.retry", side_effect=Retry()) as retry:
        result = process_event.apply(args=[str(event.pk)], throw=False)

    assert result.state == "RETRY"
    event = refreshed(event)
    assert event.status == Status.FAILED
    assert "PlatformInboundMessage" in event.last_error
    assert "alerts down" in event.last_error
    assert event.workspace_id is None
    retry.assert_called_once()
    assert retry.call_args.kwargs["max_retries"] == MAX_RETRIES


# --- requeue_stuck_events -------------------------------------------------------------------


def test_requeue_stuck_events(django_capture_on_commit_callbacks):
    long_ago = timezone.now() - timedelta(minutes=20)
    stuck = WebhookEventFactory(status=Status.PROCESSING, attempts=1)
    never_enqueued = WebhookEventFactory(status=Status.RECEIVED)
    in_flight = WebhookEventFactory(status=Status.PROCESSING, attempts=1)
    failed = WebhookEventFactory(status=Status.FAILED, attempts=6)
    done = WebhookEventFactory(status=Status.PROCESSED, attempts=1)
    for event in (stuck, never_enqueued, failed, done):
        backdate(event, updated_at=long_ago)

    with (
        mock.patch.object(process_event, "delay") as delay,
        django_capture_on_commit_callbacks(execute=True),
    ):
        count = requeue_stuck_events.delay().result

    assert count == 2
    assert {c.args[0] for c in delay.call_args_list} == {str(stuck.pk), str(never_enqueued.pk)}
    assert refreshed(stuck).status == Status.RECEIVED
    assert refreshed(in_flight).status == Status.PROCESSING
    assert refreshed(failed).status == Status.FAILED
    assert refreshed(done).status == Status.PROCESSED


def test_requeued_event_gets_processed(
    recorder, connected_number, django_capture_on_commit_callbacks
):
    event = make_event("text_message.json", status=Status.PROCESSING, attempts=1)
    backdate(event, updated_at=timezone.now() - timedelta(minutes=16))

    with django_capture_on_commit_callbacks(execute=True):
        requeue_stuck_events.delay()

    event = refreshed(event)
    assert event.status == Status.PROCESSED
    assert event.attempts == 2
    assert len(recorder.of(events.InboundMessage)) == 1


# --- purge_old_events -----------------------------------------------------------------------


def test_purge_old_events(settings):
    settings.WEBHOOK_EVENT_RETENTION_DAYS = 30
    old = timezone.now() - timedelta(days=31)
    old_processed = WebhookEventFactory(status=Status.PROCESSED)
    old_unroutable = WebhookEventFactory(status=Status.UNROUTABLE)
    old_failed = WebhookEventFactory(status=Status.FAILED)
    old_received = WebhookEventFactory(status=Status.RECEIVED)
    recent_processed = WebhookEventFactory(status=Status.PROCESSED)
    for event in (old_processed, old_unroutable, old_failed, old_received):
        backdate(event, created_at=old)

    assert purge_old_events.delay().result == 2

    remaining = set(WebhookEvent.objects.values_list("pk", flat=True))
    assert remaining == {old_failed.pk, old_received.pk, recent_processed.pk}
