"""Demo billing data for ``manage.py seed_demo``: a Growth trial, a billing profile and two paid
invoices. Idempotent."""

from datetime import timedelta

from django.utils import timezone

from . import services
from .models import Invoice

# Sample Maharashtra GSTIN with a valid check character (not a real business of ours).
DEMO_GSTIN = "27AAPFU0939F1ZV"


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
    for index, months_ago in enumerate((2, 1), start=1):
        payment_id = f"pay_demo{workspace.pk.hex[:12]}{index}"
        if Invoice.objects.filter(razorpay_payment_id=payment_id).exists():
            continue
        period_start = now - timedelta(days=30 * months_ago)
        services.create_paid_invoice(
            subscription=subscription,
            payment_id=payment_id,
            issued_at=period_start,
            period_start=period_start,
            period_end=period_start + timedelta(days=30),
        )
