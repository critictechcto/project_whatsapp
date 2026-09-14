"""Billing models. Money is integer paise; plan prices exclude GST."""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from common.models import TenantScopedModel, UUIDTimeStampedModel

from .gst import GST_STATE_CODES, validate_gstin, validate_state_code

PROFILE_REQUIRED_FIELDS = (
    "legal_name",
    "email",
    "address_line1",
    "city",
    "state_code",
    "postal_code",
)
PROFILE_FIELDS = (
    "legal_name",
    "gstin",
    "email",
    "address_line1",
    "address_line2",
    "city",
    "state_code",
    "postal_code",
)


class Plan(models.Model):
    """A subscription plan. ``limits`` maps metric keys to a cap; ``null`` means unlimited."""

    slug = models.SlugField(primary_key=True, max_length=32)
    name = models.CharField(max_length=64)
    monthly_price_paise = models.PositiveIntegerField(help_text="Per month, before GST.")
    annual_price_paise = models.PositiveIntegerField(help_text="Per year, before GST.")
    limits = models.JSONField(default=dict, blank=True)
    features = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "slug")

    def __str__(self) -> str:
        return self.name

    def price_paise(self, interval: str) -> int:
        return self.annual_price_paise if interval == "annual" else self.monthly_price_paise

    def limit(self, metric: str) -> int | None:
        value = (self.limits or {}).get(metric)
        return None if value is None else int(value)


class Subscription(UUIDTimeStampedModel):
    """A workspace's plan and billing state. Every workspace has one (``services``)."""

    class Status(models.TextChoices):
        TRIALING = "trialing", "Trialing"
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        HALTED = "halted", "Halted"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    class Interval(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        ANNUAL = "annual", "Annual"

    workspace = models.OneToOneField(
        "tenants.Workspace", on_delete=models.CASCADE, related_name="billing_subscription"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.TRIALING)
    interval = models.CharField(max_length=16, choices=Interval.choices, default=Interval.MONTHLY)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    # When the current Razorpay subscription first became active; null while checkout is open.
    activated_at = models.DateTimeField(null=True, blank=True)
    razorpay_subscription_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    razorpay_customer_id = models.CharField(max_length=64, blank=True)
    # Plan and interval chosen at checkout; applied when Razorpay activates the subscription.
    checkout_plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    checkout_interval = models.CharField(max_length=16, choices=Interval.choices, blank=True)

    class Meta(UUIDTimeStampedModel.Meta):
        indexes = [
            models.Index(fields=["status", "trial_ends_at"], name="billing_sub_status_trial_idx")
        ]

    def __str__(self) -> str:
        return f"{self.plan_id} ({self.status}) for workspace {self.workspace_id}"

    @property
    def checkout_in_progress(self) -> bool:
        """A Razorpay subscription was created at checkout but hasn't been activated yet."""
        return bool(self.razorpay_subscription_id) and self.activated_at is None


class BillingProfile(UUIDTimeStampedModel):
    """Buyer details printed on GST invoices."""

    workspace = models.OneToOneField(
        "tenants.Workspace", on_delete=models.CASCADE, related_name="billing_profile"
    )
    legal_name = models.CharField(max_length=255, blank=True)
    gstin = models.CharField(max_length=15, blank=True, validators=[validate_gstin])
    email = models.EmailField(blank=True)
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state_code = models.CharField(max_length=2, blank=True, validators=[validate_state_code])
    postal_code = models.CharField(max_length=6, blank=True)

    def __str__(self) -> str:
        return self.legal_name or f"Billing profile for workspace {self.workspace_id}"

    def clean(self) -> None:
        if self.gstin and self.state_code and self.gstin[:2] != self.state_code:
            raise ValidationError({"state_code": "Must match the first two digits of the GSTIN."})

    @property
    def is_complete(self) -> bool:
        return all(getattr(self, field) for field in PROFILE_REQUIRED_FIELDS)

    def snapshot(self) -> dict:
        data = {field: getattr(self, field) for field in PROFILE_FIELDS}
        data["state_name"] = GST_STATE_CODES.get(self.state_code, "")
        return data


class InvoiceSequence(models.Model):
    """Last serial issued per financial year; rows are locked while a number is allocated."""

    financial_year = models.CharField(max_length=7, primary_key=True)  # e.g. 2026-27
    last_serial = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.financial_year}: {self.last_serial}"


class Invoice(TenantScopedModel):
    """A GST tax invoice. Amounts and party details are snapshotted when it is issued."""

    class Status(models.TextChoices):
        ISSUED = "issued", "Issued"
        PAID = "paid", "Paid"
        VOID = "void", "Void"

    subscription = models.ForeignKey(
        Subscription, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices"
    )
    number = models.CharField(max_length=16, unique=True)
    financial_year = models.CharField(max_length=7)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ISSUED)
    issued_at = models.DateTimeField()
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    description = models.CharField(max_length=255, blank=True)
    plan_slug = models.CharField(max_length=32, blank=True)
    interval = models.CharField(max_length=16, blank=True)
    sac_code = models.CharField(max_length=8)
    currency = models.CharField(max_length=3, default="INR")
    gst_rate_percent = models.PositiveSmallIntegerField()
    subtotal_paise = models.PositiveIntegerField()
    cgst_paise = models.PositiveIntegerField(default=0)
    sgst_paise = models.PositiveIntegerField(default=0)
    igst_paise = models.PositiveIntegerField(default=0)
    total_paise = models.PositiveIntegerField()
    razorpay_payment_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    razorpay_invoice_id = models.CharField(max_length=64, blank=True)
    seller = models.JSONField(default=dict)
    buyer = models.JSONField(default=dict)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    total_paise=F("subtotal_paise")
                    + F("cgst_paise")
                    + F("sgst_paise")
                    + F("igst_paise")
                ),
                name="billing_invoice_total_is_sum",
            ),
            models.CheckConstraint(
                condition=Q(igst_paise=0) | Q(cgst_paise=0, sgst_paise=0),
                name="billing_invoice_igst_or_cgst_sgst",
            ),
        ]

    def __str__(self) -> str:
        return self.number

    @property
    def download_url(self) -> str | None:
        return None


class RazorpayEvent(UUIDTimeStampedModel):
    """A processed Razorpay webhook delivery, keyed by ``X-Razorpay-Event-Id`` for idempotency."""

    event_id = models.CharField(max_length=100, unique=True)
    type = models.CharField(max_length=64, blank=True)
    payload = models.JSONField(default=dict)
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.type} {self.event_id}"


class UsageRecord(TenantScopedModel):
    """Ledger of reported usage; ``key`` makes ``entitlements.record_usage`` idempotent."""

    metric = models.CharField(max_length=32)
    amount = models.IntegerField()
    key = models.CharField(max_length=255)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["workspace", "key"], name="billing_usage_record_key"),
        ]

    def __str__(self) -> str:
        return f"{self.metric} {self.amount:+d} ({self.key})"
