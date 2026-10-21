"""Demo billing data for ``manage.py seed_demo``: a Growth trial, a billing profile and two paid
invoices. Idempotent."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from . import invoices, services
from .models import Invoice

# Sample Maharashtra GSTIN with a valid check character (not a real business of ours).
DEMO_GSTIN = "27AAPFU0939F1ZV"
# Demo invoices only: what they show as paid when the plan's Razorpay price can't be read (no
# Razorpay keys or plan ids in dev). Real prices always come from Razorpay.
DEMO_FALLBACK_PRICE_PAISE = 2_499_00


def _demo_amount_paid(subscription, state_code: str) -> int:
    try:
        return services.checkout_total_paise(subscription.plan, subscription.interval, state_code)
    except services.PlanUnavailable:
        return invoices.compute_gst(
            DEMO_FALLBACK_PRICE_PAISE,
            buyer_state_code=state_code,
            seller_state_code=settings.BILLING_SELLER_STATE_CODE,
            rate_percent=services.gst_rate_percent(),
        ).total_paise


def seed(workspace) -> None:
    subscription = services.get_subscription(workspace)

    profile = services.get_billing_profile(workspace)
    if not profile.legal_name:
        profile.legal_name = f"{workspace.name} Private Limited"
        profile.gstin = DEMO_GSTIN
        profile.email = "accounts@example.com"
        profile.address_line1 = "4th Floor, Andheri Kurla Road"
        profile.address_line2 = "Andheri East"
        profile.city = "Mumbai"
        profile.state_code = DEMO_GSTIN[:2]
        profile.postal_code = "400069"
        profile.full_clean()
        profile.save()

    now = timezone.now()
    amount_paid = None
    for index, months_ago in enumerate((2, 1), start=1):
        payment_id = f"pay_demo{workspace.pk.hex[:12]}{index}"
        if Invoice.objects.filter(payment_id=payment_id).exists():
            continue
        if amount_paid is None:
            amount_paid = _demo_amount_paid(subscription, profile.state_code)
        period_start = now - timedelta(days=30 * months_ago)
        services.create_paid_invoice(
            subscription=subscription,
            payment_id=payment_id,
            issued_at=period_start,
            period_start=period_start,
            period_end=period_start + timedelta(days=30),
            amount_paid_paise=amount_paid,
        )
