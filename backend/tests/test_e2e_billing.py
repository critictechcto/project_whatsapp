"""End to end: Razorpay checkout and a signed charge webhook; an expired plan blocks contacts."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.billing import services as billing_services
from apps.billing.models import Invoice, RazorpayEvent, Subscription
from apps.billing.razorpay import FakeRazorpayClient, override_razorpay_client
from apps.billing.tests.helpers import MAHARASHTRA_PROFILE, post_webhook, subscription_event, ts
from apps.contacts.factories import ContactFactory
from apps.contacts.models import Contact

pytestmark = pytest.mark.django_db

BILLING = "/api/v1/billing"
GROWTH_MONTHLY_PAISE = 249900
GST_PAISE = 44982  # 18% of 249900


@pytest.fixture
def fake_razorpay():
    fake = FakeRazorpayClient()
    with override_razorpay_client(fake):
        yield fake


def test_checkout_and_charge_webhook_activate_and_invoice_once(
    auth_client, client, workspace, fake_razorpay
):
    owner = auth_client()
    profile = owner.patch(f"{BILLING}/billing-profile/", MAHARASHTRA_PROFILE, format="json")
    assert profile.status_code == 200, profile.content

    checkout = owner.post(
        f"{BILLING}/subscription/checkout/",
        {"plan_id": "growth", "interval": "monthly"},
        format="json",
    )

    assert checkout.status_code == 200, checkout.content
    razorpay_id = checkout.json()["subscription_id"]
    assert Subscription.objects.get(workspace=workspace).status == "pending"
    [created] = fake_razorpay.calls_to("create_subscription")
    assert created["plan_id"] == "plan_test_growth_monthly"

    now = timezone.now()
    payload = subscription_event(
        "subscription.charged",
        razorpay_id,
        plan_id="plan_test_growth_monthly",
        current_start=ts(now),
        current_end=ts(now + timedelta(days=30)),
        payment={
            "id": "pay_e2e1",
            "entity": "payment",
            "amount": GROWTH_MONTHLY_PAISE + GST_PAISE,
            "currency": "INR",
            "status": "captured",
            "invoice_id": "inv_e2e1",
        },
    )
    first = post_webhook(client, payload, event_id="evt_e2e_charged")
    duplicate = post_webhook(client, payload, event_id="evt_e2e_charged")

    assert (first.status_code, duplicate.status_code) == (200, 200)
    assert RazorpayEvent.objects.count() == 1
    subscription = Subscription.objects.get(workspace=workspace)
    assert (subscription.status, subscription.plan_id, subscription.interval) == (
        "active",
        "growth",
        "monthly",
    )
    invoice = Invoice.objects.get(workspace=workspace)  # exactly one
    assert invoice.status == "paid"
    assert invoice.subtotal_paise == GROWTH_MONTHLY_PAISE
    # Maharashtra buyer, Karnataka seller: inter-state, so IGST only.
    assert (invoice.cgst_paise, invoice.sgst_paise, invoice.igst_paise) == (0, 0, GST_PAISE)
    assert invoice.total_paise == GROWTH_MONTHLY_PAISE + GST_PAISE
    assert invoice.razorpay_payment_id == "pay_e2e1"

    body = owner.get(f"{BILLING}/subscription/").json()
    assert (body["status"], body["plan"]["id"]) == ("active", "growth")
    invoices = owner.get(f"{BILLING}/invoices/").json()["results"]
    assert [row["id"] for row in invoices] == [str(invoice.pk)]


def test_expired_subscription_blocks_new_contacts(auth_client, workspace):
    existing = ContactFactory(workspace=workspace)
    subscription = billing_services.get_subscription(workspace)
    Subscription.objects.filter(pk=subscription.pk).update(status="expired")
    client = auth_client()

    created = client.post(reverse("contacts:contact-list"), {"phone_e164": "9876543210"})
    updated = client.patch(
        reverse("contacts:contact-detail", args=[existing.pk]), {"name": "Still editable"}
    )

    assert created.status_code == 409, created.content
    error = created.json()["error"]
    assert error["code"] == "quota_exceeded"
    assert error["details"] == {"metric": "contacts", "limit": 1, "used": 1}
    assert "expired" in error["message"]
    assert updated.status_code == 200, updated.content
    assert Contact.objects.filter(workspace=workspace).count() == 1
