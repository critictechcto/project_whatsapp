"""Payment link services with the fake provider: creation, cancel, refresh, polling, tasks."""

import pickle
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.orders.factories import OrderFactory
from apps.payments import demo, services, tasks
from apps.payments.exceptions import (
    PaymentAccountInvalid,
    PaymentAccountMissing,
    PaymentProviderError,
)
from apps.payments.factories import PaymentAccountFactory
from apps.payments.models import PaymentAccount, PaymentLink
from apps.payments.schedules import BEAT_SCHEDULE
from common.events import PaymentLinkCancelled, PaymentLinkExpired, PaymentLinkPaid

pytestmark = pytest.mark.django_db


def test_create_saves_outbox_row_and_is_idempotent(make_link, fake_payments, workspace, order):
    link = make_link()

    assert link.status == PaymentLink.Status.CREATED
    assert link.provider == "razorpay"
    assert link.provider_link_id.startswith("plink_fake")
    assert link.short_url.startswith("https://pay.example.test/")
    assert link.reference_id == f"{order.number}-1"
    assert link.amount_paise == 49800
    assert link.poll_count == 0
    assert link.next_poll_at == link.created_at + timedelta(minutes=2)

    [request] = fake_payments.requests.values()
    assert request.return_url == services.return_url(link)
    assert request.notes == {"workspace_id": str(workspace.pk), "order_id": str(order.pk)}

    again = make_link()
    assert again.pk == link.pk
    assert fake_payments.calls_to("create_link") == [link.reference_id]


def test_create_requires_a_usable_account(workspace, order, fake_payments):
    kwargs = {
        "workspace": workspace,
        "order_id": order.pk,
        "reference_id": "SS-1-1",
        "amount_paise": 100,
        "description": "x",
        "customer_name": "x",
        "customer_phone_e164": "+919876543210",
        "expire_by": timezone.now() + timedelta(minutes=30),
    }
    with pytest.raises(PaymentAccountMissing):
        services.create_payment_link(**kwargs)

    account = PaymentAccountFactory(workspace=workspace, key_secret="")
    with pytest.raises(PaymentAccountMissing):
        services.create_payment_link(**kwargs)

    account.key_secret = "secret"
    account.status = PaymentAccount.Status.INVALID
    account.save()
    with pytest.raises(PaymentAccountInvalid):
        services.create_payment_link(**kwargs)
    assert not PaymentLink.objects.exists()
    assert fake_payments.calls == []


def test_retryable_create_error_keeps_the_row_creating(make_link, fake_payments):
    fake_payments.fail_next("create_link")

    with pytest.raises(PaymentProviderError) as caught:
        make_link()

    assert caught.value.retryable
    link = PaymentLink.objects.get()
    assert link.status == PaymentLink.Status.CREATING
    assert link.last_error

    retried = make_link()
    assert retried.pk == link.pk
    assert retried.status == PaymentLink.Status.CREATED
    assert retried.last_error == ""


def test_non_retryable_create_error_fails_the_link(make_link, fake_payments):
    fake_payments.fail_next(
        "create_link", PaymentProviderError("Bad phone.", provider="razorpay", status_code=400)
    )

    with pytest.raises(PaymentProviderError):
        make_link()

    link = PaymentLink.objects.get()
    assert link.status == PaymentLink.Status.FAILED
    assert make_link().status == PaymentLink.Status.FAILED
    assert len(fake_payments.calls_to("create_link")) == 1


def test_auth_error_on_create_marks_the_account_invalid(make_link, fake_payments, account):
    fake_payments.fail_next(
        "create_link", PaymentProviderError("Unauthorized", provider="razorpay", status_code=401)
    )

    with pytest.raises(PaymentAccountInvalid):
        make_link()

    account.refresh_from_db()
    assert account.status == PaymentAccount.Status.INVALID
    assert PaymentLink.objects.get().status == PaymentLink.Status.FAILED


def test_refresh_paid_emits_once(
    make_link, fake_payments, payment_events, django_capture_on_commit_callbacks
):
    link = make_link()
    fake_payments.mark_paid(link.provider_link_id, payment_id="pay_123")

    with django_capture_on_commit_callbacks(execute=True):
        refreshed = services.refresh_payment_link(link)
        again = services.refresh_payment_link(link)
        services.apply_link_state(link, fake_payments.links[link.provider_link_id])

    assert refreshed.status == again.status == PaymentLink.Status.PAID
    assert refreshed.provider_payment_id == "pay_123"
    assert refreshed.paid_at is not None
    assert refreshed.next_poll_at is None
    assert len(fake_payments.calls_to("fetch_link")) == 1
    [event] = payment_events
    assert isinstance(event, PaymentLinkPaid)
    assert event.payment_link_id == link.pk
    assert event.order_id == link.order_id
    assert event.workspace_id == link.workspace_id
    assert event.provider == "razorpay"
    assert event.provider_link_id == link.provider_link_id
    assert event.provider_payment_id == "pay_123"
    assert event.amount_paise == 49800
    assert event.currency == "INR"


@pytest.mark.parametrize(
    "changes",
    [{"amount_paise": 100}, {"currency": "USD"}],
)
def test_amount_or_currency_mismatch_never_confirms(
    make_link, fake_payments, payment_events, django_capture_on_commit_callbacks, changes
):
    link = make_link()
    fake_payments.mark_paid(link.provider_link_id, **changes)

    with django_capture_on_commit_callbacks(execute=True):
        refreshed = services.refresh_payment_link(link)

    assert refreshed.status == PaymentLink.Status.CREATED
    assert "not confirmed" in refreshed.last_error
    assert payment_events == []


def test_gateway_link_for_another_amount_never_confirms(make_link, fake_payments, payment_events):
    link = make_link()
    fake_payments.mark_paid(link.provider_link_id)
    fake_payments.set_state(link.provider_link_id, amount_paise=100, amount_paid_paise=49800)

    assert services.refresh_payment_link(link).status == PaymentLink.Status.CREATED


def test_partial_payment_is_logged_and_never_confirms(
    make_link, fake_payments, payment_events, django_capture_on_commit_callbacks, caplog
):
    link = make_link()
    fake_payments.mark_partially_paid(link.provider_link_id, 10000)

    with django_capture_on_commit_callbacks(execute=True):
        refreshed = services.refresh_payment_link(link)

    assert refreshed.status == PaymentLink.Status.CREATED
    assert "Partial payment" in refreshed.last_error
    assert "partially paid" in caplog.text
    assert payment_events == []


@pytest.mark.parametrize(
    ("mark", "status", "event_class"),
    [
        ("mark_expired", PaymentLink.Status.EXPIRED, PaymentLinkExpired),
        ("mark_cancelled", PaymentLink.Status.CANCELLED, PaymentLinkCancelled),
    ],
)
def test_gateway_expiry_and_cancellation_emit_once(
    make_link,
    fake_payments,
    payment_events,
    django_capture_on_commit_callbacks,
    mark,
    status,
    event_class,
):
    link = make_link()
    getattr(fake_payments, mark)(link.provider_link_id)

    with django_capture_on_commit_callbacks(execute=True):
        assert services.refresh_payment_link(link).status == status
        assert services.refresh_payment_link(link).status == status

    [event] = payment_events
    assert isinstance(event, event_class)
    assert event.payment_link_id == link.pk


def test_cancel_open_link_is_idempotent(
    make_link, fake_payments, payment_events, django_capture_on_commit_callbacks
):
    link = make_link()

    with django_capture_on_commit_callbacks(execute=True):
        cancelled = services.cancel_payment_link(link)
        again = services.cancel_payment_link(link)

    assert cancelled.status == again.status == PaymentLink.Status.CANCELLED
    assert cancelled.cancelled_at is not None
    assert len(fake_payments.calls_to("cancel_link")) == 1
    assert [type(e) for e in payment_events] == [PaymentLinkCancelled]


def test_cancel_never_cancels_a_paid_link(
    make_link, fake_payments, payment_events, django_capture_on_commit_callbacks
):
    link = make_link()
    fake_payments.mark_paid(link.provider_link_id)

    with django_capture_on_commit_callbacks(execute=True):
        result = services.cancel_payment_link(link)
        after = services.cancel_payment_link(link)

    assert result.status == after.status == PaymentLink.Status.PAID
    assert fake_payments.links[link.provider_link_id].status == "paid"
    assert len(fake_payments.calls_to("cancel_link")) == 1
    assert [type(e) for e in payment_events] == [PaymentLinkPaid]


def test_cancel_a_link_still_being_created_closes_it_locally(make_link, fake_payments):
    fake_payments.fail_next("create_link")
    with pytest.raises(PaymentProviderError):
        make_link()
    link = PaymentLink.objects.get()

    assert services.cancel_payment_link(link).status == PaymentLink.Status.CANCELLED
    assert fake_payments.calls_to("cancel_link") == []


def _start_link(make_link):
    link = make_link()
    start = link.created_at
    PaymentLink.objects.filter(pk=link.pk).update(expires_at=start + timedelta(minutes=30))
    return link, start


def test_poll_schedule_and_final_expiry(
    make_link, fake_payments, payment_events, django_capture_on_commit_callbacks
):
    link, start = _start_link(make_link)
    polled_at = []

    with django_capture_on_commit_callbacks(execute=True):
        for minute in range(0, 46):
            before = len(fake_payments.calls_to("fetch_link"))
            services.poll_due_links(now=start + timedelta(minutes=minute, seconds=1))
            if len(fake_payments.calls_to("fetch_link")) > before:
                polled_at.append(minute)

    assert polled_at == [2, 4, 6, 10, 15, 20, 25, 30, 32]
    link.refresh_from_db()
    assert link.status == PaymentLink.Status.EXPIRED
    assert link.next_poll_at is None
    assert link.poll_count == 9
    assert fake_payments.calls_to("cancel_link") == [link.provider_link_id]
    assert [type(e) for e in payment_events] == [PaymentLinkExpired]


def test_late_worker_goes_straight_to_the_final_poll(make_link, fake_payments):
    link, start = _start_link(make_link)

    services.poll_due_links(now=start + timedelta(hours=2))

    link.refresh_from_db()
    assert link.status == PaymentLink.Status.EXPIRED
    assert len(fake_payments.calls_to("fetch_link")) == 1


def test_final_poll_confirms_a_paid_link(make_link, fake_payments):
    link, start = _start_link(make_link)
    fake_payments.mark_paid(link.provider_link_id)

    services.poll_due_links(now=start + timedelta(minutes=33))

    link.refresh_from_db()
    assert link.status == PaymentLink.Status.PAID
    assert fake_payments.calls_to("cancel_link") == []


def test_poll_survives_gateway_errors(make_link, fake_payments):
    link, start = _start_link(make_link)
    fake_payments.fail_next("fetch_link")

    assert services.poll_due_links(now=start + timedelta(minutes=2, seconds=1)) == 1

    link.refresh_from_db()
    assert link.status == PaymentLink.Status.CREATED
    assert link.poll_count == 1
    assert link.next_poll_at == start + timedelta(minutes=4)


def test_final_poll_errors_retry_then_expire(make_link, fake_payments):
    link, start = _start_link(make_link)
    PaymentLink.objects.filter(pk=link.pk).update(poll_count=8, next_poll_at=start)
    now = start + timedelta(minutes=32)

    # The first final poll plus MAX_FINAL_POLL_RETRIES - 1 retries fail; the next one expires.
    for _ in range(services.MAX_FINAL_POLL_RETRIES):
        fake_payments.fail_next("fetch_link")
        services.poll_due_links(now=now)
        link.refresh_from_db()
        assert link.status == PaymentLink.Status.CREATED
        now = link.next_poll_at

    fake_payments.fail_next("fetch_link")
    services.poll_due_links(now=now)
    link.refresh_from_db()
    assert link.status == PaymentLink.Status.EXPIRED


def test_poll_ignores_links_that_are_not_due_or_closed(make_link, fake_payments, workspace):
    link, start = _start_link(make_link)
    PaymentLink.objects.filter(pk=link.pk).update(status=PaymentLink.Status.PAID)

    assert services.poll_due_links(now=start + timedelta(hours=1)) == 0
    assert fake_payments.calls_to("fetch_link") == []


def test_create_link_task(make_link, fake_payments, workspace, order, account):
    kwargs = {
        "workspace_id": str(workspace.pk),
        "order_id": str(order.pk),
        "reference_id": f"{order.number}-2",
        "amount_paise": 49800,
        "description": "Order",
        "customer_name": "Asha",
        "customer_phone_e164": "+919876543210",
        "expire_by": (timezone.now() + timedelta(minutes=30)).isoformat(),
    }

    link_id = tasks.create_link.delay(**kwargs).get()

    assert PaymentLink.objects.get(pk=link_id).status == PaymentLink.Status.CREATED

    fake_payments.fail_next("create_link")
    # Eager apply() runs the scheduled retry at once, so the second attempt succeeds.
    result = tasks.create_link.apply(kwargs={**kwargs, "reference_id": "X-3"}, throw=False)
    assert fake_payments.calls_to("create_link").count("X-3") == 2
    assert PaymentLink.objects.get(pk=result.result).status == PaymentLink.Status.CREATED

    fake_payments.fail_next(
        "create_link", PaymentProviderError("Bad.", provider="razorpay", status_code=400)
    )
    assert tasks.create_link.delay(**{**kwargs, "reference_id": "X-4"}).get() is None


def test_poll_task_and_beat_entry(make_link, fake_payments):
    make_link()

    assert tasks.poll_open_links.delay().get() == 0
    assert BEAT_SCHEDULE["payments.poll_open_links"]["task"] == "payments.poll_open_links"


def test_provider_error_pickles():
    error = PaymentProviderError("Down.", provider="cashfree", status_code=503, retryable=True)

    # Round-trips our own object (Celery result backend); no untrusted data.
    restored = pickle.loads(pickle.dumps(error))  # noqa: S301

    assert str(restored) == "Down."
    assert (restored.provider, restored.status_code, restored.retryable) == (
        "cashfree",
        503,
        True,
    )


def test_demo_seed_is_idempotent(workspace):
    demo.seed(workspace)
    demo.seed(workspace)

    account = PaymentAccount.objects.get(workspace=workspace)
    assert account.provider == "razorpay"
    assert account.mode == "test"
    assert account.key_secret == ""
    assert account.status == PaymentAccount.Status.NOT_CONFIGURED


def test_links_in_other_workspaces_are_not_touched(make_link, fake_payments, other_workspace):
    other = OrderFactory(workspace=other_workspace)
    PaymentAccountFactory(workspace=other_workspace)
    link = make_link()

    assert services.cancel_payment_link(link).workspace_id != other.workspace_id
