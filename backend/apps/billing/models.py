"""Billing models. Money is integer paise. Plan prices come from Razorpay plans
(:mod:`apps.billing.prices`); UpChatz stores no price of its own."""

from django.conf import settings
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


class BillingProvider(models.TextChoices):
    """The gateway that took a payment (``settings.BILLING_PROVIDERS``)."""

    RAZORPAY = "razorpay", "Razorpay"
    CASHFREE = "cashfree", "Cashfree"


class PaymentMode(models.TextChoices):
    """How a paid plan is paid: a Razorpay auto-pay subscription or one prepaid period."""

    AUTOPAY = "autopay", "Auto-pay"
    ONE_TIME = "one_time", "Pay once"


class Plan(models.Model):
    """A subscription plan. ``limits`` maps metric keys to a cap; ``null`` means unlimited.

    The price of each interval is the amount of its Razorpay plan (:mod:`apps.billing.prices`)."""

    slug = models.SlugField(primary_key=True, max_length=32)
    name = models.CharField(max_length=64)
    razorpay_plan_id_monthly = models.CharField(
        max_length=64,
        blank=True,
        help_text="Razorpay plan (plan_...) billed monthly. Blank: RAZORPAY_PLAN_IDS, if set.",
    )
    razorpay_plan_id_annual = models.CharField(
        max_length=64,
        blank=True,
        help_text="Razorpay plan (plan_...) billed yearly. Blank: RAZORPAY_PLAN_IDS, if set.",
    )
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

    def configured_razorpay_plan_id(self, interval: str) -> str:
        """The plan's own field for ``interval`` (no settings fallback)."""
        if interval == "annual":
            return self.razorpay_plan_id_annual
        return self.razorpay_plan_id_monthly

    def settings_razorpay_plan_id(self, interval: str) -> str:
        """``RAZORPAY_PLAN_IDS[slug][interval]``, or ``""``."""
        value = ((settings.RAZORPAY_PLAN_IDS or {}).get(self.slug) or {}).get(interval)
        return value if isinstance(value, str) else ""

    def razorpay_plan_id(self, interval: str) -> str:
        """The Razorpay plan id for ``interval``: the field, else ``RAZORPAY_PLAN_IDS``, else
        ``""``."""
        return self.configured_razorpay_plan_id(interval) or self.settings_razorpay_plan_id(
            interval
        )

    def price_paise(self, interval: str) -> int | None:
        """The price before GST, from the Razorpay plan; None when this interval can't be
        bought right now. Never raises."""
        from .prices import price_paise

        return price_paise(self, interval)

    def limit(self, metric: str) -> int | None:
        value = (self.limits or {}).get(metric)
        return None if value is None else int(value)


class RazorpayPlan(models.Model):
    """A read-only copy of a Razorpay plan. Razorpay plans can't change once created, so the copy
    never goes stale. ``plan``/``interval`` record which UpChatz plan it was fetched for, so
    webhooks still map subscriptions on an older Razorpay plan."""

    id = models.CharField(primary_key=True, max_length=64, help_text="Razorpay plan_... id.")
    plan = models.ForeignKey(
        Plan, on_delete=models.SET_NULL, null=True, blank=True, related_name="razorpay_plans"
    )
    interval = models.CharField(
        max_length=16, choices=(("monthly", "Monthly"), ("annual", "Annual"))
    )
    period = models.CharField(max_length=16, help_text="Razorpay's period: monthly, yearly, ...")
    period_interval = models.PositiveSmallIntegerField(help_text="Periods per billing cycle.")
    amount_paise = models.PositiveIntegerField(
        help_text="Charged by Razorpay per cycle; GST-inclusive when GST is on."
    )
    currency = models.CharField(max_length=3)
    item_name = models.CharField(max_length=255, blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("plan_id", "interval", "-fetched_at")

    def __str__(self) -> str:
        return f"{self.id} ({self.item_name or self.interval})"


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
    # Gateway of the current paid plan; blank until one starts.
    provider = models.CharField(max_length=16, choices=BillingProvider.choices, blank=True)
    # The paid plan is prepaid (one period paid once through a ``BillingOrder``, never charged
    # again by itself) rather than a Razorpay auto-pay subscription. Cashfree plans always are.
    prepaid = models.BooleanField(default=False)
    # "<period end iso>:<days>" of the last renewal reminder, so each is sent once per period.
    renewal_reminder_key = models.CharField(max_length=64, blank=True)

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

    @property
    def is_razorpay(self) -> bool:
        """Paid through Razorpay (rows from before ``provider`` included). A Razorpay plan may
        be prepaid too: :attr:`is_autopay` means "a Razorpay subscription"."""
        if self.provider:
            return self.provider == BillingProvider.RAZORPAY
        return bool(self.razorpay_subscription_id)

    @property
    def is_cashfree(self) -> bool:
        return self.provider == BillingProvider.CASHFREE

    @property
    def is_prepaid(self) -> bool:
        """One prepaid period (a fulfilled ``BillingOrder``) that never renews by itself."""
        return self.prepaid or self.is_cashfree

    @property
    def is_autopay(self) -> bool:
        """Paid through a Razorpay subscription that charges again by itself."""
        return self.is_razorpay and not self.is_prepaid

    @property
    def payment_mode(self) -> str | None:
        """``one_time`` or ``autopay`` for the current (or last) paid plan; None before one."""
        if not self.provider:
            return None
        return PaymentMode.ONE_TIME if self.is_prepaid else PaymentMode.AUTOPAY

    @property
    def provider_or_none(self) -> str | None:
        return self.provider or None

    @property
    def auto_renews(self) -> bool:
        """A Razorpay subscription charges again by itself; prepaid plans never renew."""
        active = self.status == self.Status.ACTIVE
        return active and self.is_autopay and not self.cancel_at_period_end


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
    # E.164. Optional, but a Cashfree checkout needs it.
    phone = models.CharField(max_length=16, blank=True)

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
    # The gateway's payment id: Razorpay ``pay_...`` or Cashfree ``cf_payment_id``.
    payment_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    payment_provider = models.CharField(max_length=16, choices=BillingProvider.choices, blank=True)
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
    def download_url(self) -> str:
        """API path of the PDF (``apps.billing.invoice_pdf``); fetch it with the Bearer token."""
        return f"/api/v1/billing/invoices/{self.pk}/pdf/"


class BillingOrder(TenantScopedModel):
    """A prepaid plan purchase: one Razorpay or Cashfree order, fulfilled once
    (``services.fulfil_order``)."""

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"

    provider = models.CharField(max_length=16, choices=BillingProvider.choices)
    # Razorpay's ``order_...`` id, or UpChatz's own Cashfree order id (``upc_...``).
    order_id = models.CharField(max_length=64, unique=True)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="billing_orders")
    interval = models.CharField(max_length=16, choices=Subscription.Interval.choices)
    amount_paise = models.PositiveIntegerField(help_text="GST-inclusive, as charged.")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CREATED)
    # Cashfree only, cleared once paid: it only opens Cashfree Checkout.
    payment_session_id = models.CharField(max_length=512, blank=True)
    # The gateway's payment id: Razorpay ``pay_...`` or Cashfree ``cf_payment_id``.
    payment_id = models.CharField(max_length=64, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.order_id} ({self.status})"


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
