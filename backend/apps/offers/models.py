"""Offer codes and the claims buyers make by sending them (docs/contracts/services-and-offers.md).

A buyer who sends exactly a code gets a ``claimed`` claim. The next checkout marks it
``applied`` to that order; a delivered-and-paid (or completed) order, or staff at the counter,
mark it ``redeemed``. Claims of an ended offer that were never applied become ``expired``.
Money is integer paise.
"""

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q

from common.models import TenantScopedModel

CODE_PATTERN = r"^[A-Za-z0-9_-]{2,20}$"
code_validator = RegexValidator(CODE_PATTERN, "Use 2-20 letters, digits, '-' or '_'.")


class OfferCode(TenantScopedModel):
    class DiscountType(models.TextChoices):
        NONE = "none", "No discount"
        PERCENT = "percent", "Percent"
        AMOUNT = "amount", "Amount"

    class AppliesTo(models.TextChoices):
        ALL = "all", "Products and services"
        PRODUCTS = "products", "Products"
        SERVICES = "services", "Services"
        ITEMS = "items", "Chosen products or services"

    code = models.CharField(max_length=20, validators=[code_validator])  # stored upper-case
    title = models.CharField(max_length=60, blank=True)
    reply_text = models.TextField(max_length=900)
    discount_type = models.CharField(
        max_length=8, choices=DiscountType.choices, default=DiscountType.NONE
    )
    # Percent 1-90, or paise >= 100 for an amount; 0 for no discount.
    discount_value = models.PositiveIntegerField(default=0)
    max_discount_paise = models.PositiveIntegerField(null=True, blank=True)  # percent only
    min_order_paise = models.PositiveIntegerField(default=0)
    applies_to = models.CharField(max_length=8, choices=AppliesTo.choices, default=AppliesTo.ALL)
    # For ``items``: the discount and minimum order count only these catalog items.
    products = models.ManyToManyField("catalog.Product", blank=True, related_name="+")
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True)  # applied + redeemed claims
    max_uses_per_contact = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["workspace", "code"], name="offers_unique_code"),
        ]

    def __str__(self) -> str:
        return self.code

    def save(self, *args, **kwargs):
        self.code = (self.code or "").upper()
        super().save(*args, **kwargs)


class OfferClaim(TenantScopedModel):
    class Status(models.TextChoices):
        CLAIMED = "claimed", "Claimed"
        APPLIED = "applied", "Applied"
        REDEEMED = "redeemed", "Redeemed"
        EXPIRED = "expired", "Expired"

    offer = models.ForeignKey(OfferCode, on_delete=models.CASCADE, related_name="claims")
    contact = models.ForeignKey("contacts.Contact", on_delete=models.CASCADE, related_name="+")
    conversation = models.ForeignKey(
        "inbox.Conversation", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    message = models.ForeignKey(
        "inbox.Message", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    wamid = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.CLAIMED)
    order = models.ForeignKey(
        "orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    discount_paise = models.PositiveIntegerField(default=0)
    bill_paise = models.PositiveIntegerField(null=True, blank=True)
    ad_source_id = models.CharField(max_length=128, blank=True)
    ad_source_url = models.URLField(max_length=1000, blank=True)
    ad_headline = models.CharField(max_length=255, blank=True)
    ctwa_clid = models.CharField(max_length=255, blank=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)
    redeemed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["offer", "wamid"],
                condition=~Q(wamid=""),
                name="offers_claim_unique_wamid",
            ),
        ]
        indexes = [
            models.Index(fields=["workspace", "contact", "status"], name="offers_claim_contact"),
            models.Index(fields=["offer", "status"], name="offers_claim_offer_status"),
        ]

    def __str__(self) -> str:
        return f"{self.offer_id} {self.status}"

    @property
    def from_ad(self) -> bool:
        return bool(self.ad_source_id or self.ctwa_clid)
