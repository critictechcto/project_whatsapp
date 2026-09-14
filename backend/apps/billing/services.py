"""Billing workflows: the trial, Razorpay checkout and cancellation, billing profiles, GST
invoices and usage counts. Views and the webhook call these; other apps use ``entitlements``."""

import hmac
import logging
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import exceptions

from apps.contacts.models import Contact
from apps.tenants.models import Membership
from apps.whatsapp.models import PhoneNumber
from common.exceptions import Conflict, UpstreamUnavailable

from . import entitlements, invoices, razorpay
from .models import BillingProfile, Invoice, InvoiceSequence, Plan, Subscription
from .plans import TRIAL_DAYS, TRIAL_PLAN_SLUG, ensure_default_plans

logger = logging.getLogger(__name__)

Status = Subscription.Status
Interval = Subscription.Interval

CHECKOUT_NAME = "UpChatz"
# Razorpay subscription statuses meaning the customer authorised or paid.
RAZORPAY_ACTIVE_STATUSES = frozenset({"authenticated", "active"})


class BillingProfileRequired(Conflict):
    default_code = "billing_profile_required"
    default_detail = (
        "Complete the billing profile (legal name, email, address, city, state and PIN code) "
        "before checking out."
    )


class SubscriptionAlreadyActive(Conflict):
    default_code = "subscription_active"
    default_detail = (
        "This workspace already has an active subscription. Cancel it before choosing a plan."
    )


class PaymentVerificationFailed(exceptions.APIException):
    status_code = 400
    default_code = "payment_verification_failed"
    default_detail = "The payment could not be verified."


class BillingUnavailable(UpstreamUnavailable):
    default_detail = "The payment provider is unavailable. Try again shortly."


# --- Subscription ---------------------------------------------------------------------------


def trial_plan() -> Plan:
    plan = Plan.objects.filter(slug=TRIAL_PLAN_SLUG).first()
    if plan is None:
        # A migration seeds the catalogue; restore it if the table was flushed (e.g. by tests).
        ensure_default_plans()
        plan = Plan.objects.get(slug=TRIAL_PLAN_SLUG)
    return plan


def get_subscription(workspace, *, for_update: bool = False) -> Subscription:
    """The workspace's subscription, created on first use as a 14-day Growth trial (no card)."""
    queryset = Subscription.objects.select_related("plan")
    if for_update:
        queryset = queryset.select_for_update(of=("self",))
    subscription = queryset.filter(workspace=workspace).first()
    if subscription is None:
        subscription, _ = Subscription.objects.get_or_create(
            workspace=workspace,
            defaults={
                "plan": trial_plan,
                "status": Status.TRIALING,
                "interval": Interval.MONTHLY,
                "trial_ends_at": lambda: timezone.now() + timedelta(days=TRIAL_DAYS),
            },
        )
        if for_update:
            subscription = queryset.get(pk=subscription.pk)
    return subscription


def timestamp_to_datetime(value: object) -> datetime | None:
    """Razorpay unix timestamps → aware datetimes; None for missing or invalid values."""
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        return None
    return datetime.fromtimestamp(value, tz=UTC)


def period_end_after(start: datetime, interval: str) -> datetime:
    """Fallback period end when Razorpay doesn't send one."""
    return start + timedelta(days=365 if interval == Interval.ANNUAL else 30)


def apply_period(subscription: Subscription, entity: dict) -> None:
    start = timestamp_to_datetime(entity.get("current_start"))
    end = timestamp_to_datetime(entity.get("current_end"))
    if start is not None:
        subscription.current_period_start = start
    if end is not None:
        subscription.current_period_end = end


def _plan_for_entity(subscription: Subscription, entity: dict) -> tuple[Plan, str]:
    match = razorpay.plan_for_razorpay_plan_id(entity.get("plan_id"))
    if match is not None:
        plan = Plan.objects.filter(slug=match[0]).first()
        if plan is not None:
            return plan, match[1]
    if subscription.checkout_plan_id:
        return subscription.checkout_plan, subscription.checkout_interval or subscription.interval
    return subscription.plan, subscription.interval


def activate(subscription: Subscription, entity: dict) -> bool:
    """Apply an authorised or charged Razorpay subscription entity. Saves the subscription.

    Returns False (and changes nothing) when this Razorpay subscription already ended, so a late
    or out-of-order event can't revive it.
    """
    if subscription.status in (Status.CANCELLED, Status.EXPIRED) and subscription.activated_at:
        logger.info("Ignoring activation of ended subscription %s", subscription.pk)
        return False
    plan, interval = _plan_for_entity(subscription, entity)
    subscription.plan = plan
    subscription.interval = interval
    subscription.status = Status.ACTIVE
    subscription.activated_at = subscription.activated_at or timezone.now()
    subscription.checkout_plan = None
    subscription.checkout_interval = ""
    apply_period(subscription, entity)
    customer_id = entity.get("customer_id")
    if isinstance(customer_id, str) and customer_id:
        subscription.razorpay_customer_id = customer_id[:64]
    subscription.save()
    return True


def abandon_checkout(subscription: Subscription, *, keep_trial: bool, now: datetime) -> None:
    """Forget an unactivated Razorpay subscription. Doesn't save.

    During a trial the workspace returns to ``trialing`` when ``keep_trial`` (``expired`` if the
    trial is over), otherwise it is ``cancelled``. A halted workspace becomes ``cancelled``.
    """
    subscription.razorpay_subscription_id = None
    subscription.checkout_plan = None
    subscription.checkout_interval = ""
    if subscription.status in (Status.TRIALING, Status.PENDING):
        if not keep_trial:
            subscription.status = Status.CANCELLED
        elif subscription.trial_ends_at and subscription.trial_ends_at > now:
            subscription.status = Status.TRIALING
        else:
            subscription.status = Status.EXPIRED
    elif subscription.status == Status.HALTED:
        subscription.status = Status.CANCELLED


def _checkout_description(plan: Plan, interval: str) -> str:
    period = "year" if interval == Interval.ANNUAL else "month"
    price = invoices.format_inr(plan.price_paise(interval))
    return f"{plan.name} plan: {price} + {settings.BILLING_GST_RATE_PERCENT}% GST per {period}"


def _cancel_quietly(razorpay_subscription_id: str) -> None:
    try:
        razorpay.get_razorpay_client().cancel_subscription(
            razorpay_subscription_id, at_cycle_end=False
        )
    except razorpay.RazorpayError as exc:
        logger.warning(
            "Could not cancel superseded Razorpay subscription %s: %s",
            razorpay_subscription_id,
            exc,
        )


def start_checkout(*, workspace, plan_slug: str, interval: str) -> dict:
    """Create (or reuse) a Razorpay subscription and return Razorpay Checkout options.

    The Subscription keeps its current plan (and trial) until Razorpay activates it; a trialing
    workspace shows ``pending`` meanwhile.
    """
    plan = Plan.objects.filter(slug=plan_slug, is_active=True).first()
    if plan is None:
        raise exceptions.ValidationError({"plan_id": ["This plan is not available."]})
    profile = get_billing_profile(workspace)
    if not profile.is_complete:
        raise BillingProfileRequired()
    subscription = get_subscription(workspace)
    if subscription.status == Status.ACTIVE:
        raise SubscriptionAlreadyActive()

    try:
        razorpay_plan_id = razorpay.plan_id_for(plan.slug, interval)
        client = razorpay.get_razorpay_client()
        subscription_id = _reusable_checkout(client, subscription, plan, interval)
        if subscription_id is None:
            entity = client.create_subscription(
                plan_id=razorpay_plan_id,
                total_count=razorpay.TOTAL_COUNT[interval],
                notes={"workspace_id": str(workspace.pk), "plan": plan.slug, "interval": interval},
            )
            subscription_id = entity.get("id")
            if not isinstance(subscription_id, str) or not subscription_id:
                raise razorpay.RazorpayError("Razorpay did not return a subscription id.")
    except razorpay.RazorpayError as exc:
        logger.error("Razorpay checkout failed for workspace %s: %s", workspace.pk, exc)
        raise BillingUnavailable() from exc

    superseded = None
    with transaction.atomic():
        subscription = get_subscription(workspace, for_update=True)
        if subscription.status == Status.ACTIVE:
            raise SubscriptionAlreadyActive()
        if subscription.razorpay_subscription_id != subscription_id:
            superseded = subscription.razorpay_subscription_id
            subscription.razorpay_subscription_id = subscription_id
            subscription.activated_at = None
        subscription.checkout_plan = plan
        subscription.checkout_interval = interval
        if subscription.status == Status.TRIALING:
            subscription.status = Status.PENDING
        subscription.save()
    if superseded:
        _cancel_quietly(superseded)
    entitlements.clear_cache(workspace)
    return {
        "key_id": settings.RAZORPAY_KEY_ID,
        "subscription_id": subscription_id,
        "name": CHECKOUT_NAME,
        "description": _checkout_description(plan, interval),
        "prefill": {"name": profile.legal_name, "email": profile.email},
    }


def _reusable_checkout(client, subscription: Subscription, plan: Plan, interval: str) -> str | None:
    """The open checkout's Razorpay id when it is for the same plan and still unpaid."""
    if not (
        subscription.checkout_in_progress
        and subscription.checkout_plan_id == plan.slug
        and subscription.checkout_interval == interval
    ):
        return None
    entity = client.fetch_subscription(subscription.razorpay_subscription_id)
    return subscription.razorpay_subscription_id if entity.get("status") == "created" else None


def verify_checkout(
    *, workspace, payment_id: str, subscription_id: str, signature: str
) -> Subscription:
    """Check the Checkout signature, then sync the status from Razorpay when it's reachable.

    The webhook stays the source of truth, so the subscription may still be ``pending``.
    """
    subscription = get_subscription(workspace)
    expected_id = (subscription.razorpay_subscription_id or "").encode()
    valid = (
        bool(expected_id)
        and hmac.compare_digest(expected_id, subscription_id.encode())
        and razorpay.checkout_signature_is_valid(
            payment_id=payment_id,
            subscription_id=subscription_id,
            signature=signature,
            secret=settings.RAZORPAY_KEY_SECRET,
        )
    )
    if not valid:
        logger.warning("Razorpay checkout verification failed for workspace %s", workspace.pk)
        raise PaymentVerificationFailed()

    try:
        entity = razorpay.get_razorpay_client().fetch_subscription(subscription_id)
    except razorpay.RazorpayError as exc:
        logger.warning("Could not fetch Razorpay subscription %s: %s", subscription_id, exc)
        return subscription
    if entity.get("status") in RAZORPAY_ACTIVE_STATUSES:
        with transaction.atomic():
            subscription = get_subscription(workspace, for_update=True)
            if subscription.razorpay_subscription_id == subscription_id:
                activate(subscription, entity)
        entitlements.clear_cache(workspace)
    return subscription


def cancel_subscription(*, workspace, at_period_end: bool) -> Subscription:
    """Cancel at the end of the paid period (or trial) or immediately. Idempotent once ended."""
    subscription = get_subscription(workspace)
    in_checkout = subscription.checkout_in_progress
    if subscription.status in (Status.CANCELLED, Status.EXPIRED) and not in_checkout:
        return subscription

    razorpay_id = subscription.razorpay_subscription_id
    at_cycle_end = at_period_end and subscription.status == Status.ACTIVE and not in_checkout
    if razorpay_id and in_checkout:
        _cancel_quietly(razorpay_id)  # nothing was charged; don't block the local change
    elif razorpay_id:
        try:
            razorpay.get_razorpay_client().cancel_subscription(
                razorpay_id, at_cycle_end=at_cycle_end
            )
        except razorpay.RazorpayError as exc:
            logger.error("Razorpay cancellation failed for workspace %s: %s", workspace.pk, exc)
            raise BillingUnavailable() from exc

    now = timezone.now()
    with transaction.atomic():
        subscription = get_subscription(workspace, for_update=True)
        if in_checkout and subscription.razorpay_subscription_id == razorpay_id:
            abandon_checkout(subscription, keep_trial=at_period_end, now=now)
            subscription.cancel_at_period_end = subscription.status == Status.TRIALING
        elif (subscription.status == Status.TRIALING and at_period_end) or (
            subscription.status == Status.ACTIVE and at_cycle_end
        ):
            subscription.cancel_at_period_end = True
        elif subscription.status not in (Status.CANCELLED, Status.EXPIRED):
            subscription.status = Status.CANCELLED
            subscription.cancel_at_period_end = False
        subscription.save()
    entitlements.clear_cache(workspace)
    return subscription


def expire_trials(*, now: datetime | None = None) -> int:
    """Mark trials that ended without an activated Razorpay subscription as ``expired``."""
    now = now or timezone.now()
    count = (
        Subscription.objects.filter(
            status__in=[Status.TRIALING, Status.PENDING],
            activated_at__isnull=True,
            trial_ends_at__lte=now,
        )
        .filter(Q(current_period_end__isnull=True) | Q(current_period_end__lte=now))
        .update(status=Status.EXPIRED, cancel_at_period_end=False, updated_at=now)
    )
    if count:
        logger.info("Expired %d trial subscription(s)", count)
    return count


# --- Billing profile ------------------------------------------------------------------------


def get_billing_profile(workspace) -> BillingProfile:
    profile, _ = BillingProfile.objects.get_or_create(workspace=workspace)
    return profile


# --- Usage ----------------------------------------------------------------------------------


def usage_count(workspace, metric: str) -> int:
    if metric == entitlements.WHATSAPP_NUMBERS:
        return (
            PhoneNumber.objects.filter(workspace=workspace)
            .exclude(registration_status=PhoneNumber.RegistrationStatus.DEREGISTERED)
            .count()
        )
    if metric == entitlements.MEMBERS:
        return Membership.objects.filter(workspace=workspace).count()
    if metric == entitlements.CONTACTS:
        return Contact.objects.filter(workspace=workspace).count()
    raise ValueError(f"Unknown entitlement metric {metric!r}.")


def usage_counts(workspace) -> dict[str, int]:
    return {metric: usage_count(workspace, metric) for metric in entitlements.METRICS}


# --- Invoices -------------------------------------------------------------------------------


def allocate_invoice_number(at: datetime) -> tuple[str, str]:
    """Next ``(number, financial year)`` in the series for ``at``.

    Locks the year's counter row until the surrounding transaction ends, so concurrent callers
    get consecutive numbers and a rolled-back invoice leaves no gap.
    """
    fiscal_year = invoices.financial_year(at)
    with transaction.atomic():
        InvoiceSequence.objects.bulk_create(
            [InvoiceSequence(financial_year=fiscal_year)], ignore_conflicts=True
        )
        sequence = InvoiceSequence.objects.select_for_update().get(financial_year=fiscal_year)
        sequence.last_serial += 1
        sequence.save(update_fields=["last_serial", "updated_at"])
    return invoices.format_invoice_number(fiscal_year, sequence.last_serial), fiscal_year


def seller_snapshot() -> dict:
    return {
        "legal_name": settings.BILLING_SELLER_LEGAL_NAME,
        "gstin": settings.BILLING_SELLER_GSTIN,
        "state_code": settings.BILLING_SELLER_STATE_CODE,
        "address": settings.BILLING_SELLER_ADDRESS,
    }


def create_paid_invoice(
    *,
    subscription: Subscription,
    payment_id: str,
    issued_at: datetime,
    period_start: datetime,
    period_end: datetime,
    razorpay_invoice_id: str = "",
    amount_paid_paise: int | None = None,
) -> tuple[Invoice, bool]:
    """Issue a paid GST invoice for a Razorpay payment. Idempotent per ``payment_id``."""
    existing = Invoice.objects.filter(razorpay_payment_id=payment_id).first()
    if existing is not None:
        return existing, False

    plan, interval = subscription.plan, subscription.interval
    profile = BillingProfile.objects.filter(workspace_id=subscription.workspace_id).first()
    buyer = profile.snapshot() if profile is not None else {}
    gst = invoices.compute_gst(
        plan.price_paise(interval),
        buyer_state_code=buyer.get("state_code", ""),
        seller_state_code=settings.BILLING_SELLER_STATE_CODE,
        rate_percent=settings.BILLING_GST_RATE_PERCENT,
    )
    if amount_paid_paise is not None and amount_paid_paise != gst.total_paise:
        logger.warning(
            "Razorpay payment %s was %s paise but the invoice total is %s paise; check that the "
            "Razorpay plan amount includes GST",
            payment_id,
            amount_paid_paise,
            gst.total_paise,
        )
    with transaction.atomic():
        number, fiscal_year = allocate_invoice_number(issued_at)
        invoice = Invoice.objects.create(
            workspace_id=subscription.workspace_id,
            subscription=subscription,
            number=number,
            financial_year=fiscal_year,
            status=Invoice.Status.PAID,
            issued_at=issued_at,
            period_start=period_start,
            period_end=period_end,
            description=f"UpChatz {plan.name} plan ({interval})",
            plan_slug=plan.slug,
            interval=interval,
            sac_code=settings.BILLING_SAC_CODE,
            gst_rate_percent=gst.rate_percent,
            subtotal_paise=gst.subtotal_paise,
            cgst_paise=gst.cgst_paise,
            sgst_paise=gst.sgst_paise,
            igst_paise=gst.igst_paise,
            total_paise=gst.total_paise,
            razorpay_payment_id=payment_id,
            razorpay_invoice_id=razorpay_invoice_id,
            seller=seller_snapshot(),
            buyer=buyer,
        )
    return invoice, True
