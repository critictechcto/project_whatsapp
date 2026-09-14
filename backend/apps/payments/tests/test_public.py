"""The buyer return page and the optional merchant webhook (both public, not in the schema)."""

import base64
import hashlib
import hmac
import json

import pytest

from apps.orders.factories import OrderFactory, StoreSettingsFactory
from apps.payments.factories import PaymentAccountFactory, PaymentLinkFactory
from apps.payments.models import PaymentLink, PaymentWebhookEvent
from apps.payments.views import format_inr
from common.events import PaymentLinkPaid
from common.razorpay import hmac_sha256_hex

pytestmark = pytest.mark.django_db

RETURN = "/pay/return/"
WEBHOOK = "/webhooks/payments/merchants/"


def return_page(client, link, **params):
    return client.get(f"{RETURN}{link.pk}/", params)


def test_return_page_paid(
    api_client,
    workspace,
    order,
    make_link,
    fake_payments,
    payment_events,
    django_capture_on_commit_callbacks,
):
    StoreSettingsFactory(workspace=workspace, store_name="Sharma Sweets")
    link = make_link()
    fake_payments.mark_paid(link.provider_link_id)

    with django_capture_on_commit_callbacks(execute=True):
        response = return_page(api_client, link)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    assert response["Cache-Control"] == "no-store"
    html = response.content.decode()
    assert f"Payment received for order {order.number}. You can go back to WhatsApp." in html
    assert "Sharma Sweets" in html
    assert "₹498.00" in html
    digits = order.phone_number.phone_e164.lstrip("+")
    assert f'href="https://wa.me/{digits}"' in html
    assert http_equiv_refresh(html) is False
    assert str(workspace.pk) not in html
    assert link.provider_link_id not in html
    assert PaymentLink.objects.get(pk=link.pk).status == PaymentLink.Status.PAID
    assert [type(e) for e in payment_events] == [PaymentLinkPaid]


def http_equiv_refresh(html: str) -> bool:
    return 'http-equiv="refresh"' in html


def test_return_page_pending_never_trusts_query_parameters(api_client, make_link, order):
    link = make_link()

    response = return_page(
        api_client,
        link,
        razorpay_payment_id="pay_fake",
        razorpay_payment_link_id=link.provider_link_id,
        razorpay_payment_link_reference_id=link.reference_id,
        razorpay_payment_link_status="paid",
        razorpay_signature="forged",
    )

    assert response.status_code == 200
    html = response.content.decode()
    assert "We&#x27;re confirming your payment" in html
    assert order.number in html
    assert http_equiv_refresh(html)
    assert PaymentLink.objects.get(pk=link.pk).status == PaymentLink.Status.CREATED


def test_return_page_gateway_down_still_renders(api_client, make_link, fake_payments):
    link = make_link()
    fake_payments.fail_next("fetch_link")

    response = return_page(api_client, link)

    assert response.status_code == 200
    assert "confirming your payment" in response.content.decode()


def test_return_page_expired_link(api_client, make_link, fake_payments):
    link = make_link()
    fake_payments.mark_expired(link.provider_link_id)

    response = return_page(api_client, link)

    assert response.status_code == 200
    assert "no longer active" in response.content.decode()


def test_return_page_unknown_link(api_client):
    response = api_client.get(f"{RETURN}00000000-0000-0000-0000-000000000000/")

    assert response.status_code == 404
    assert response["Content-Type"].startswith("text/html")
    assert api_client.post(f"{RETURN}00000000-0000-0000-0000-000000000000/").status_code == 405


def test_return_page_is_throttled_per_ip(api_client, make_link):
    link = make_link()

    statuses = [return_page(api_client, link).status_code for _ in range(31)]

    assert statuses[:30] == [200] * 30
    assert statuses[30] == 429
    other_ip = api_client.get(f"{RETURN}{link.pk}/", REMOTE_ADDR="10.0.0.9")
    assert other_ip.status_code == 200


def test_format_inr():
    assert format_inr(49800) == "₹498.00"
    assert format_inr(123456789) == "₹12,34,567.89"
    assert format_inr(100000) == "₹1,000.00"
    assert format_inr(5) == "₹0.05"


# --- Webhook ---------------------------------------------------------------------------------


def test_webhook_unknown_token(api_client):
    response = api_client.post(f"{WEBHOOK}nope/", data=b"{}", content_type="application/json")

    assert response.status_code == 404


def test_fake_webhook_applies_state_and_dedupes(
    api_client,
    account,
    make_link,
    fake_payments,
    payment_events,
    django_capture_on_commit_callbacks,
):
    link = make_link()
    fake_payments.mark_paid(link.provider_link_id)
    headers, body = fake_payments.webhook(link.provider_link_id, event_id="evt_1")
    url = f"{WEBHOOK}{account.webhook_token}/"

    with django_capture_on_commit_callbacks(execute=True):
        first = api_client.post(
            url, data=body, content_type="application/json", HTTP_X_FAKE_SIGNATURE="valid"
        )
        second = api_client.post(
            url, data=body, content_type="application/json", HTTP_X_FAKE_SIGNATURE="valid"
        )

    assert first.status_code == second.status_code == 200
    assert PaymentLink.objects.get(pk=link.pk).status == PaymentLink.Status.PAID
    event = PaymentWebhookEvent.objects.get()
    assert event.event_id == "evt_1"
    assert event.processed_at is not None
    assert [type(e) for e in payment_events] == [PaymentLinkPaid]
    assert headers


def test_fake_webhook_without_state_refreshes(api_client, account, make_link, fake_payments):
    link = make_link()
    fake_payments.mark_paid(link.provider_link_id)
    _, body = fake_payments.webhook(link.provider_link_id, event_id="evt_2", include_state=False)

    response = api_client.post(
        f"{WEBHOOK}{account.webhook_token}/",
        data=body,
        content_type="application/json",
        HTTP_X_FAKE_SIGNATURE="valid",
    )

    assert response.status_code == 200
    assert fake_payments.calls_to("fetch_link") == [link.provider_link_id]
    assert PaymentLink.objects.get(pk=link.pk).status == PaymentLink.Status.PAID


def test_webhook_gateway_error_still_200_and_can_be_retried(
    api_client, account, make_link, fake_payments
):
    link = make_link()
    _, body = fake_payments.webhook(link.provider_link_id, event_id="evt_3", include_state=False)
    url = f"{WEBHOOK}{account.webhook_token}/"
    fake_payments.fail_next("fetch_link")

    kwargs = {"data": body, "content_type": "application/json", "HTTP_X_FAKE_SIGNATURE": "valid"}
    assert api_client.post(url, **kwargs).status_code == 200
    assert PaymentWebhookEvent.objects.get().processed_at is None

    fake_payments.mark_paid(link.provider_link_id)
    assert api_client.post(url, **kwargs).status_code == 200
    assert PaymentWebhookEvent.objects.get().processed_at is not None
    assert PaymentLink.objects.get(pk=link.pk).status == PaymentLink.Status.PAID


def razorpay_body(link, *, amount_paid):
    entity = {
        "id": link.provider_link_id,
        "amount": link.amount_paise,
        "amount_paid": amount_paid,
        "currency": "INR",
        "status": "paid",
        "reference_id": link.reference_id,
        "short_url": link.short_url,
    }
    payment = {"id": "pay_Webhook1", "amount": amount_paid, "status": "captured"}
    return json.dumps(
        {
            "entity": "event",
            "event": "payment_link.paid",
            "contains": ["payment_link", "payment"],
            "payload": {"payment_link": {"entity": entity}, "payment": {"entity": payment}},
            "created_at": 1757834706,
        }
    ).encode()


def test_razorpay_webhook_signature_and_dedupe(
    api_client, workspace, payment_events, django_capture_on_commit_callbacks
):
    account = PaymentAccountFactory(workspace=workspace)
    link = PaymentLinkFactory(
        order=OrderFactory(workspace=workspace, status="pending_payment", payment_status="unpaid"),
        provider_link_id="plink_Webhook1",
    )
    body = razorpay_body(link, amount_paid=link.amount_paise)
    url = f"{WEBHOOK}{account.webhook_token}/"
    signature = hmac_sha256_hex(account.webhook_secret, body)

    bad = api_client.post(
        url, data=body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE="0" * 64
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "invalid_signature"

    with django_capture_on_commit_callbacks(execute=True):
        for _ in range(2):
            response = api_client.post(
                url,
                data=body,
                content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE=signature,
                HTTP_X_RAZORPAY_EVENT_ID="evt_rzp_1",
            )
            assert response.status_code == 200

    link.refresh_from_db()
    assert link.status == PaymentLink.Status.PAID
    assert link.provider_payment_id == "pay_Webhook1"
    assert PaymentWebhookEvent.objects.get().event_id == "evt_rzp_1"
    assert len(payment_events) == 1


def test_razorpay_webhook_partial_amount_never_confirms(api_client, workspace):
    account = PaymentAccountFactory(workspace=workspace)
    link = PaymentLinkFactory(
        order=OrderFactory(workspace=workspace, status="pending_payment", payment_status="unpaid"),
        provider_link_id="plink_Webhook2",
    )
    body = razorpay_body(link, amount_paid=100)

    response = api_client.post(
        f"{WEBHOOK}{account.webhook_token}/",
        data=body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=hmac_sha256_hex(account.webhook_secret, body),
    )

    assert response.status_code == 200
    link.refresh_from_db()
    assert link.status == PaymentLink.Status.CREATED
    assert "not confirmed" in link.last_error


def cashfree_body(link) -> bytes:
    return json.dumps(
        {
            "data": {
                "link_id": link.provider_link_id,
                "link_status": "PAID",
                "link_currency": "INR",
                "link_amount": "498.00",
                "link_amount_paid": "498.00",
                "order": {
                    "order_id": "CFPay_1",
                    "transaction_id": 99,
                    "transaction_status": "SUCCESS",
                },
            },
            "type": "PAYMENT_LINK_EVENT",
            "version": 1,
            "event_time": "2026-09-14T12:55:06+05:30",
        }
    ).encode()


def test_cashfree_webhook_signature_and_dedupe(
    api_client, workspace, payment_events, django_capture_on_commit_callbacks
):
    account = PaymentAccountFactory(
        workspace=workspace,
        provider="cashfree",
        key_id="TEST10123",
        key_secret="cf-secret",
        webhook_secret="",
    )
    link = PaymentLinkFactory(
        order=OrderFactory(
            workspace=workspace,
            status="pending_payment",
            payment_status="unpaid",
            total_paise=49800,
        ),
        provider="cashfree",
        provider_link_id="SS-2001-1",
    )
    body = cashfree_body(link)
    timestamp = "1757834706"
    digest = hmac.new(b"cf-secret", timestamp.encode() + body, hashlib.sha256).digest()
    headers = {
        "HTTP_X_WEBHOOK_TIMESTAMP": timestamp,
        "HTTP_X_WEBHOOK_SIGNATURE": base64.b64encode(digest).decode(),
    }
    url = f"{WEBHOOK}{account.webhook_token}/"

    bad = api_client.post(
        url,
        data=body,
        content_type="application/json",
        HTTP_X_WEBHOOK_TIMESTAMP=timestamp,
        HTTP_X_WEBHOOK_SIGNATURE="bad",
    )
    assert bad.status_code == 400

    with django_capture_on_commit_callbacks(execute=True):
        for _ in range(2):
            assert (
                api_client.post(url, data=body, content_type="application/json", **headers)
            ).status_code == 200

    link.refresh_from_db()
    assert link.status == PaymentLink.Status.PAID
    assert link.provider_payment_id == "99"
    assert PaymentWebhookEvent.objects.get().event_id.startswith("sha256:")
    assert len(payment_events) == 1
