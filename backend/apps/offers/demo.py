"""Demo offer for ``manage.py seed_demo``: a DIWALI code with a few claims.

Rows are written directly (no messages, no events) and keyed on natural keys (the code, demo
wamids, phone numbers), so running the seeder again changes nothing.
"""

from datetime import timedelta

from django.utils import timezone

from apps.contacts.models import Contact
from common.phone import to_wa_id

from .models import OfferClaim, OfferCode

CODE = "DIWALI"
OFFER = {
    "title": "Diwali 10% off",
    "reply_text": (
        "Happy Diwali! 🪔 You get 10% off your next order (up to ₹200). "
        "Tap Shop now to start, or show this chat at our shop."
    ),
    "discount_type": OfferCode.DiscountType.PERCENT,
    "discount_value": 10,
    "max_discount_paise": 20000,
    "min_order_paise": 49900,
    "applies_to": OfferCode.AppliesTo.ALL,
    "max_uses": 500,
    "max_uses_per_contact": 1,
    "is_active": True,
}

# (name, phone, status, from_ad, bill_paise)
CLAIMS = [
    ("Asha Verma", "+919812345701", OfferClaim.Status.REDEEMED, True, 129900),
    ("Vikram Singh", "+919812345702", OfferClaim.Status.CLAIMED, True, None),
    ("Meera Nair", "+919812345703", OfferClaim.Status.CLAIMED, False, None),
    ("Neha Joshi", "+919812345709", OfferClaim.Status.REDEEMED, False, 64900),
]


def seed(workspace) -> None:
    now = timezone.now()
    offer, _ = OfferCode.objects.get_or_create(
        workspace=workspace,
        code=CODE,
        defaults={**OFFER, "ends_at": now + timedelta(days=21)},
    )
    for index, (name, phone, status, from_ad, bill_paise) in enumerate(CLAIMS, start=1):
        contact, _ = Contact.objects.get_or_create(
            workspace=workspace,
            phone_e164=phone,
            defaults={"name": name, "wa_id": to_wa_id(phone)},
        )
        ad = (
            {
                "ad_source_id": "120210000000000001",
                "ad_source_url": "https://fb.me/upchatz-demo-diwali",
                "ad_headline": "Diwali sweets: 10% off on WhatsApp",
                "ctwa_clid": f"demo-clid-{index}",
            }
            if from_ad
            else {}
        )
        redeemed = status == OfferClaim.Status.REDEEMED
        OfferClaim.objects.get_or_create(
            offer=offer,
            wamid=f"wamid.DEMO-OFFER-{index}",
            defaults={
                "workspace": workspace,
                "contact": contact,
                "status": status,
                "bill_paise": bill_paise,
                "discount_paise": min(bill_paise * 10 // 100, 20000) if bill_paise else 0,
                "redeemed_at": now - timedelta(days=index) if redeemed else None,
                **ad,
            },
        )
