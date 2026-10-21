"""Billing workflows: the trial, checkout (Razorpay auto-pay subscriptions, or prepaid one-time
orders on Razorpay or Cashfree), cancellation, prepaid expiry and renewal reminders, billing
profiles, GST invoices and usage counts. Views and the webhooks call these; other apps use
``entitlements``.

``settings.BILLING_PROVIDER`` picks the gateway for new checkouts only; existing subscriptions
keep their own flow (docs/contracts/billing-cashfree.md). A paid plan is either auto-pay (a
Razorpay subscription that charges again by itself) or prepaid (``Subscription.prepaid``: one
period bought through a ``BillingOrder``, renewed by paying again)."""

import hmac
import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import partial

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import exceptions

from apps.contacts.models import Contact
from apps.tenants.models import Membership
from apps.whatsapp.models import PhoneNumber
from common.cashfree import cashfree_phone
from common.exceptions import Conflict, UpstreamUnavailable
from common.roles import Role

from . import cashfree, entitlements, invoices, razorpay
from .invoices import INDIA_TZ
from .models import (
    BillingOrder,
    BillingProfile,
    BillingProvider,
    Invoice,
    InvoiceSequence,
    PaymentMode,
    Plan,
    Subscription,
)
from .plans import TRIAL_DAYS, TRIAL_PLAN_SLUG, ensure_default_plans

logger = logging.getLogger(__name__)

Status = Subscription.Status
Interval = Subscription.Interval
OrderStatus = BillingOrder.Status

CHECKOUT_NAME = "UpChatz"
# Razorpay subscription statuses meaning the customer authorised or paid.
RAZORPAY_ACTIVE_STATUSES = frozenset({"authenticated", "active"})
# A Cashfree order can be paid for this long after checkout.
CASHFREE_ORDER_TTL = timedelta(hours=1)
# Cashfree order statuses that end the order without a payment.
CASHFREE_ENDED_STATUSES = {
    "EXPIRED": OrderStatus.EXPIRED,
    "TERMINATED": OrderStatus.FAILED,
    "TERMINATION_REQUESTED": OrderStatus.FAILED,
}
# Days before a prepaid plan ends when its renewal reminder goes out (largest first).
RENEWAL_REMINDER_DAYS = (7, 1)
# Prepaid plans (``Subscription.is_prepaid``): Cashfree plans are prepaid whatever the flag says.
PREPAID = Q(prepaid=True) | Q(provider=BillingProvider.CASHFREE)


class BillingProfileRequired(Conflict):
    default_code = "billing_profile_required"
    default_detail = (
        "Complete the billing profile (legal name, email, address, city, state and PIN code) "
        "before checking out."
    )
    phone_detail = (
        "Complete the billing profile (legal name, email, phone, address, city, state and PIN "
        "code) before checking out. Cashfree needs a phone number for payment receipts."
    )


class PaymentNotCompleted(Conflict):
    default_code = "payment_not_completed"
    default_detail = "The payment wasn't completed. You haven't been charged."


class SubscriptionAlreadyActive(Conflict):
    default_code = "subscription_active"
    default_detail = (
        "This workspace already has an active subscription. Cancel it before choosing a plan."
    )
    prepaid_detail = "You can switch to auto-pay when your paid period ends."


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
    subscription.provider = BillingProvider.RAZORPAY
    subscription.prepaid = False
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


def gst_rate_percent() -> int:
    """The GST rate charged on plans: 0 while ``BILLING_GST_ENABLED`` is off (not registered)."""
    return settings.BILLING_GST_RATE_PERCENT if settings.BILLING_GST_ENABLED else 0


def _checkout_description(plan: Plan, interval: str) -> str:
    period = "year" if interval == Interval.ANNUAL else "month"
    price = invoices.format_inr(plan.price_paise(interval))
    rate = gst_rate_percent()
    gst = f" + {rate}% GST" if rate else ""
    return f"{plan.name} plan: {price}{gst} per {period}"


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


def _checkout_session(
    provider: str, *, payment_mode: str, plan: Plan, interval: str, profile
) -> dict:
    """The ``CheckoutSession`` fields every provider shares; the others start as null."""
    return {
        "provider": provider,
        "payment_mode": payment_mode,
        "name": CHECKOUT_NAME,
        "description": _checkout_description(plan, interval),
        "prefill": {"name": profile.legal_name, "email": profile.email},
        "key_id": None,
        "subscription_id": None,
        "order_id": None,
        "payment_session_id": None,
        "mode": None,
        "amount_paise": None,
    }


def default_payment_mode() -> str:
    """Auto-pay on Razorpay; Cashfree only sells prepaid periods."""
    if settings.BILLING_PROVIDER == BillingProvider.CASHFREE:
        return PaymentMode.ONE_TIME
    return PaymentMode.AUTOPAY


def start_checkout(
    *, workspace, plan_slug: str, interval: str, payment_mode: str | None = None
) -> dict:
    """Start a checkout on ``settings.BILLING_PROVIDER`` and return the ``CheckoutSession``.

    ``payment_mode`` is ``autopay`` (a Razorpay subscription) or ``one_time`` (a prepaid order);
    it defaults to auto-pay on Razorpay and one-time on Cashfree, which has no auto-pay.
    """
    payment_mode = payment_mode or default_payment_mode()
    cashfree_checkout = settings.BILLING_PROVIDER == BillingProvider.CASHFREE
    if cashfree_checkout and payment_mode != PaymentMode.ONE_TIME:
        raise exceptions.ValidationError(
            {"payment_mode": ["Auto-pay isn't available; choose one_time."]}
        )
    plan = Plan.objects.filter(slug=plan_slug, is_active=True).first()
    if plan is None:
        raise exceptions.ValidationError({"plan_id": ["This plan is not available."]})
    if cashfree_checkout:
        return start_cashfree_checkout(workspace=workspace, plan=plan, interval=interval)
    if payment_mode == PaymentMode.ONE_TIME:
        return start_razorpay_order_checkout(workspace=workspace, plan=plan, interval=interval)
    return start_razorpay_checkout(workspace=workspace, plan=plan, interval=interval)


def _refuse_autopay_while_active(subscription: Subscription) -> None:
    if subscription.status == Status.ACTIVE:
        if subscription.is_prepaid:
            raise SubscriptionAlreadyActive(SubscriptionAlreadyActive.prepaid_detail)
        raise SubscriptionAlreadyActive()


def start_razorpay_checkout(*, workspace, plan: Plan, interval: str) -> dict:
    """Create (or reuse) a Razorpay auto-pay subscription and return Razorpay Checkout options.

    The Subscription keeps its current plan (and trial) until Razorpay activates it; a trialing
    workspace shows ``pending`` meanwhile. An active plan blocks it: an auto-pay one must be
    cancelled first, a prepaid one must run out first.
    """
    profile = get_billing_profile(workspace)
    if not profile.is_complete:
        raise BillingProfileRequired()
    subscription = get_subscription(workspace)
    _refuse_autopay_while_active(subscription)

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
        _refuse_autopay_while_active(subscription)
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
    session = _checkout_session(
        BillingProvider.RAZORPAY,
        payment_mode=PaymentMode.AUTOPAY,
        plan=plan,
        interval=interval,
        profile=profile,
    )
    session.update(key_id=settings.RAZORPAY_KEY_ID, subscription_id=subscription_id)
    return session


def _refuse_prepaid_while_autopay_active(subscription: Subscription) -> None:
    """A prepaid plan may be renewed or changed while active; an auto-pay one must be
    cancelled first."""
    if subscription.status == Status.ACTIVE and not subscription.is_prepaid:
        raise SubscriptionAlreadyActive()


def start_razorpay_order_checkout(*, workspace, plan: Plan, interval: str) -> dict:
    """Create a Razorpay order for one prepaid period and return Razorpay Checkout options.

    The subscription doesn't change until the order is paid (:func:`fulfil_order`).
    """
    profile = get_billing_profile(workspace)
    if not profile.is_complete:
        raise BillingProfileRequired()
    subscription = get_subscription(workspace)
    _refuse_prepaid_while_autopay_active(subscription)

    amount_paise = checkout_total_paise(plan, interval, profile.state_code)
    try:
        entity = razorpay.get_razorpay_client().create_order(
            amount=amount_paise,
            currency="INR",
            receipt=f"upc_{uuid.uuid4().hex}",
            notes={"workspace_id": str(workspace.pk), "plan": plan.slug, "interval": interval},
        )
        order_id = entity.get("id")
        if not isinstance(order_id, str) or not order_id or len(order_id) > 64:
            raise razorpay.RazorpayError("Razorpay did not return an order id.")
    except razorpay.RazorpayError as exc:
        logger.error("Razorpay order checkout failed for workspace %s: %s", workspace.pk, exc)
        raise BillingUnavailable() from exc

    BillingOrder.objects.create(
        workspace=workspace,
        provider=BillingProvider.RAZORPAY,
        order_id=order_id,
        plan=plan,
        interval=interval,
        amount_paise=amount_paise,
    )
    session = _checkout_session(
        BillingProvider.RAZORPAY,
        payment_mode=PaymentMode.ONE_TIME,
        plan=plan,
        interval=interval,
        profile=profile,
    )
    session.update(key_id=settings.RAZORPAY_KEY_ID, order_id=order_id, amount_paise=amount_paise)
    return session


def checkout_total_paise(plan: Plan, interval: str, buyer_state_code: str) -> int:
    """The amount charged (GST-inclusive when GST is on): exactly the invoice total."""
    return invoices.compute_gst(
        plan.price_paise(interval),
        buyer_state_code=buyer_state_code,
        seller_state_code=settings.BILLING_SELLER_STATE_CODE,
        rate_percent=gst_rate_percent(),
    ).total_paise


def paise_to_rupees(amount_paise: int) -> float:
    """Cashfree amounts are rupees with up to 2 decimals (a JSON number)."""
    return float(Decimal(amount_paise) / 100)


def rupees_to_paise(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        amount = Decimal(str(value)) * 100
    except InvalidOperation:
        return None
    return int(amount) if amount == amount.to_integral_value() else None


def cashfree_order_body(
    *, order_id: str, workspace, plan: Plan, interval: str, profile, amount_paise: int, now
) -> dict:
    frontend = settings.FRONTEND_URL.rstrip("/")
    order_meta = {"return_url": f"{frontend}/app/w/{workspace.pk}/billing?cf_order_id={order_id}"}
    notify_url = f"{settings.PUBLIC_API_BASE_URL.rstrip('/')}/webhooks/cashfree/billing/"
    # Cashfree accepts only HTTPS notify URLs; local dev relies on verify alone.
    if notify_url.startswith("https://"):
        order_meta["notify_url"] = notify_url
    return {
        "order_id": order_id,
        "order_amount": paise_to_rupees(amount_paise),
        "order_currency": "INR",
        "customer_details": {
            "customer_id": workspace.pk.hex,
            "customer_phone": cashfree_phone(profile.phone),
            "customer_email": profile.email,
            "customer_name": profile.legal_name,
        },
        "order_meta": order_meta,
        "order_expiry_time": (now + CASHFREE_ORDER_TTL)
        .astimezone(INDIA_TZ)
        .isoformat(timespec="seconds"),
        "order_note": _checkout_description(plan, interval),
        "order_tags": {"workspace_id": str(workspace.pk), "plan": plan.slug, "interval": interval},
    }


def start_cashfree_checkout(*, workspace, plan: Plan, interval: str) -> dict:
    """Create a Cashfree order for one prepaid period and return Cashfree Checkout options.

    The subscription doesn't change until the order is paid (:func:`fulfil_order`). An active
    prepaid plan may check out again to renew or change plan; an active auto-pay subscription
    must be cancelled first.
    """
    profile = get_billing_profile(workspace)
    if not (profile.is_complete and profile.phone):
        raise BillingProfileRequired(BillingProfileRequired.phone_detail)
    subscription = get_subscription(workspace)
    _refuse_prepaid_while_autopay_active(subscription)

    amount_paise = checkout_total_paise(plan, interval, profile.state_code)
    order_id = f"upc_{uuid.uuid4().hex}"
    body = cashfree_order_body(
        order_id=order_id,
        workspace=workspace,
        plan=plan,
        interval=interval,
        profile=profile,
        amount_paise=amount_paise,
        now=timezone.now(),
    )
    try:
        order = cashfree.get_cashfree_client().create_order(body)
        session_id = order.get("payment_session_id")
        if not isinstance(session_id, str) or not session_id:
            raise cashfree.CashfreeError("Cashfree did not return a payment session.")
    except cashfree.CashfreeError as exc:
        logger.error("Cashfree checkout failed for workspace %s: %s", workspace.pk, exc)
        raise BillingUnavailable() from exc

    BillingOrder.objects.create(
        workspace=workspace,
        provider=BillingProvider.CASHFREE,
        order_id=order_id,
        plan=plan,
        interval=interval,
        amount_paise=amount_paise,
        payment_session_id=session_id,
    )
    session = _checkout_session(
        BillingProvider.CASHFREE,
        payment_mode=PaymentMode.ONE_TIME,
        plan=plan,
        interval=interval,
        profile=profile,
    )
    session.update(
        order_id=order_id,
        payment_session_id=session_id,
        mode=settings.CASHFREE_ENV,
        amount_paise=amount_paise,
    )
    return session


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


def verify_cashfree_checkout(*, workspace, order_id: str) -> Subscription:
    """Ask Cashfree whether the workspace's order is paid; fulfil it when it is.

    Raises ``PaymentVerificationFailed`` for an unknown order (or another workspace's),
    ``PaymentNotCompleted`` while it is unpaid and ``BillingUnavailable`` when Cashfree is down.
    """
    order = BillingOrder.objects.filter(workspace=workspace, order_id=order_id).first()
    if order is None:
        logger.warning("Cashfree verification for an unknown order in workspace %s", workspace.pk)
        raise PaymentVerificationFailed()
    if order.status == OrderStatus.PAID:
        return get_subscription(workspace)

    try:
        client = cashfree.get_cashfree_client()
        remote = client.fetch_order(order_id)
        status = remote.get("order_status")
        payment_id = _successful_payment_id(client, order_id) if status == "PAID" else ""
    except cashfree.CashfreeError as exc:
        logger.warning("Could not fetch Cashfree order %s: %s", order_id, exc)
        raise BillingUnavailable() from exc
    if status != "PAID":
        ended = CASHFREE_ENDED_STATUSES.get(status)
        if ended is not None:
            BillingOrder.objects.filter(pk=order.pk, status=OrderStatus.CREATED).update(
                status=ended, updated_at=timezone.now()
            )
        raise PaymentNotCompleted()
    if not payment_id:
        # Paid, but the payment isn't listed yet: key the invoice on the order instead.
        logger.warning("Cashfree order %s is paid but has no SUCCESS payment listed", order_id)
        payment_id = order_id
    fulfil_order(order_id, payment_id=payment_id)
    return get_subscription(workspace)


def _successful_payment_id(client, order_id: str) -> str:
    for payment in client.fetch_order_payments(order_id):
        if payment.get("payment_status") == "SUCCESS" and payment.get("cf_payment_id"):
            return str(payment["cf_payment_id"])[:64]
    return ""


def verify_razorpay_order_checkout(
    *, workspace, payment_id: str, order_id: str, signature: str
) -> Subscription:
    """Check the Checkout signature, then ask Razorpay whether the order is paid; fulfil it
    when it is.

    Raises ``PaymentVerificationFailed`` for a bad signature or an unknown order (or another
    workspace's), ``PaymentNotCompleted`` while it is unpaid and ``BillingUnavailable`` when
    Razorpay is down.
    """
    order = BillingOrder.objects.filter(
        workspace=workspace, provider=BillingProvider.RAZORPAY, order_id=order_id
    ).first()
    valid = order is not None and razorpay.order_signature_is_valid(
        payment_id=payment_id,
        order_id=order_id,
        signature=signature,
        secret=settings.RAZORPAY_KEY_SECRET,
    )
    if not valid:
        logger.warning("Razorpay order verification failed for workspace %s", workspace.pk)
        raise PaymentVerificationFailed()
    if order.status == OrderStatus.PAID:
        return get_subscription(workspace)

    try:
        client = razorpay.get_razorpay_client()
        status = client.fetch_order(order_id).get("status")
        captured = (
            [
                str(payment["id"])[:64]
                for payment in client.fetch_order_payments(order_id)
                if payment.get("status") == "captured" and payment.get("id")
            ]
            if status == "paid"
            else []
        )
    except razorpay.RazorpayError as exc:
        logger.warning("Could not fetch Razorpay order %s: %s", order_id, exc)
        raise BillingUnavailable() from exc
    if status != "paid":
        raise PaymentNotCompleted()
    if payment_id not in captured and captured:
        payment_id = captured[0]
    fulfil_order(order_id, payment_id=payment_id[:64])
    return get_subscription(workspace)


def fulfil_order(order_id: str, *, payment_id: str, paid_at: datetime | None = None) -> bool:
    """Apply a paid prepaid order (Razorpay or Cashfree): extend or start the plan and issue the
    GST invoice.

    Paying for the plan and interval of an active prepaid plan extends it from its period end,
    whichever gateway took either payment; anything else starts a new period now. Idempotent:
    the order row is locked and an order that is already paid is left alone. Returns True when
    this call fulfilled it.
    """
    now = timezone.now()
    with transaction.atomic():
        order = (
            BillingOrder.objects.select_for_update()
            .select_related("plan", "workspace")
            .filter(order_id=order_id)
            .first()
        )
        if order is None or order.status == OrderStatus.PAID:
            return False
        subscription = get_subscription(order.workspace, for_update=True)
        renewal = (
            subscription.status == Status.ACTIVE
            and subscription.is_prepaid
            and subscription.plan_id == order.plan_id
            and subscription.interval == order.interval
            and subscription.current_period_end is not None
            and subscription.current_period_end > now
        )
        if renewal:
            period_start = subscription.current_period_end
        else:
            period_start = now
            subscription.current_period_start = now
        period_end = period_end_after(period_start, order.interval)

        # A Razorpay subscription still open at Razorpay (an unpaid checkout, or one that would
        # retry charges) is cancelled there once this commits, and no longer tracked here.
        live_razorpay = subscription.checkout_in_progress or subscription.status in (
            Status.ACTIVE,
            Status.PENDING,
            Status.HALTED,
        )
        superseded = subscription.razorpay_subscription_id if live_razorpay else None
        subscription.plan = order.plan
        subscription.interval = order.interval
        subscription.status = Status.ACTIVE
        subscription.provider = order.provider
        subscription.prepaid = True
        subscription.current_period_end = period_end
        subscription.cancel_at_period_end = False
        subscription.activated_at = subscription.activated_at or now
        subscription.checkout_plan = None
        subscription.checkout_interval = ""
        subscription.razorpay_subscription_id = None
        subscription.save()

        create_paid_invoice(
            subscription=subscription,
            payment_id=payment_id,
            payment_provider=order.provider,
            issued_at=paid_at or now,
            period_start=period_start,
            period_end=period_end,
            amount_paid_paise=order.amount_paise,
        )
        order.status = OrderStatus.PAID
        order.paid_at = paid_at or now
        order.payment_id = payment_id
        order.period_start = period_start
        order.period_end = period_end
        order.payment_session_id = ""
        order.save()
        if superseded:
            transaction.on_commit(partial(_cancel_quietly, superseded))
    entitlements.clear_cache(order.workspace)
    logger.info(
        "Fulfilled %s order %s for workspace %s", order.provider, order_id, order.workspace_id
    )
    return True


def verify_checkout(**data) -> Subscription:
    """``CheckoutVerifyRequest``: a Cashfree ``order_id``, or the Razorpay payment id and
    signature with ``razorpay_order_id`` (one-time) or ``razorpay_subscription_id`` (auto-pay)."""
    workspace = data.pop("workspace")
    if data.get("order_id"):
        return verify_cashfree_checkout(workspace=workspace, order_id=data["order_id"])
    if data.get("razorpay_order_id"):
        return verify_razorpay_order_checkout(
            workspace=workspace,
            payment_id=data["razorpay_payment_id"],
            order_id=data["razorpay_order_id"],
            signature=data["razorpay_signature"],
        )
    return verify_razorpay_checkout(
        workspace=workspace,
        payment_id=data["razorpay_payment_id"],
        subscription_id=data["razorpay_subscription_id"],
        signature=data["razorpay_signature"],
    )


def verify_razorpay_checkout(
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
    """Cancel at the end of the paid period (or trial) or immediately. Idempotent once ended.

    A prepaid plan (any gateway) has nothing to cancel at the gateway; only an open auto-pay
    checkout started after it ended is cancelled at Razorpay.
    """
    subscription = get_subscription(workspace)
    in_checkout = subscription.checkout_in_progress
    if subscription.status in (Status.CANCELLED, Status.EXPIRED) and not in_checkout:
        return subscription

    razorpay_id = (
        subscription.razorpay_subscription_id
        if in_checkout or not subscription.is_prepaid
        else None
    )
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


def expire_prepaid(*, now: datetime | None = None) -> int:
    """End prepaid plans whose paid period is over: ``cancelled`` when the owner cancelled at
    period end, otherwise ``expired``. Returns how many changed."""
    now = now or timezone.now()
    ended = Subscription.objects.filter(PREPAID, status=Status.ACTIVE, current_period_end__lte=now)
    cancelled = ended.filter(cancel_at_period_end=True).update(
        status=Status.CANCELLED, cancel_at_period_end=False, updated_at=now
    )
    expired = ended.filter(cancel_at_period_end=False).update(status=Status.EXPIRED, updated_at=now)
    if cancelled or expired:
        logger.info(
            "Ended %d prepaid plan(s): %d cancelled, %d expired",
            cancelled + expired,
            cancelled,
            expired,
        )
    return cancelled + expired


def renewal_reminder_days(period_end: datetime, now: datetime) -> int | None:
    """Which reminder is due (7 or 1), counting calendar days in India; None when neither."""
    days_left = (
        timezone.localtime(period_end, INDIA_TZ).date() - timezone.localtime(now, INDIA_TZ).date()
    ).days
    due = [days for days in RENEWAL_REMINDER_DAYS if days_left <= days]
    return min(due) if due else None


def renewal_reminder_recipients(subscription: Subscription) -> list[str]:
    """The workspace owners and the billing-profile email, without duplicates."""
    emails = list(
        Membership.objects.filter(workspace_id=subscription.workspace_id, role=Role.OWNER)
        .order_by("created_at")
        .values_list("user__email", flat=True)
    )
    profile = BillingProfile.objects.filter(workspace_id=subscription.workspace_id).first()
    if profile is not None and profile.email:
        emails.append(profile.email)
    seen: set[str] = set()
    recipients = []
    for email in emails:
        if email and email.lower() not in seen:
            seen.add(email.lower())
            recipients.append(email)
    return recipients


def send_renewal_reminders(*, now: datetime | None = None) -> int:
    """Queue renewal reminders for prepaid plans ending within 7 days (then within 1 day).

    Each reminder goes out once per period: ``renewal_reminder_key`` is claimed with a
    conditional update before the emails are queued on commit. Returns how many were claimed.
    """
    from .tasks import send_renewal_reminder_email

    now = now or timezone.now()
    horizon = now + timedelta(days=max(RENEWAL_REMINDER_DAYS) + 1)
    candidates = Subscription.objects.filter(
        PREPAID,
        status=Status.ACTIVE,
        cancel_at_period_end=False,
        current_period_end__gt=now,
        current_period_end__lte=horizon,
    ).only("id", "workspace_id", "current_period_end", "renewal_reminder_key")
    sent = 0
    for subscription in candidates:
        days = renewal_reminder_days(subscription.current_period_end, now)
        if days is None:
            continue
        key = f"{subscription.current_period_end.isoformat()}:{days}"
        if subscription.renewal_reminder_key == key:
            continue
        with transaction.atomic():
            claimed = Subscription.objects.filter(
                pk=subscription.pk, renewal_reminder_key=subscription.renewal_reminder_key
            ).update(renewal_reminder_key=key, updated_at=now)
            if not claimed:
                continue
            for email in renewal_reminder_recipients(subscription):
                transaction.on_commit(
                    partial(send_renewal_reminder_email.delay, str(subscription.pk), email, key),
                    robust=True,
                )
        sent += 1
    if sent:
        logger.info("Queued %d renewal reminder(s)", sent)
    return sent


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
    payment_provider: str = BillingProvider.RAZORPAY,
    razorpay_invoice_id: str = "",
    amount_paid_paise: int | None = None,
) -> tuple[Invoice, bool]:
    """Issue a paid GST invoice for a gateway payment. Idempotent per ``payment_id``."""
    existing = Invoice.objects.filter(payment_id=payment_id).first()
    if existing is not None:
        return existing, False

    plan, interval = subscription.plan, subscription.interval
    profile = BillingProfile.objects.filter(workspace_id=subscription.workspace_id).first()
    buyer = profile.snapshot() if profile is not None else {}
    gst = invoices.compute_gst(
        plan.price_paise(interval),
        buyer_state_code=buyer.get("state_code", ""),
        seller_state_code=settings.BILLING_SELLER_STATE_CODE,
        rate_percent=gst_rate_percent(),
    )
    if amount_paid_paise is not None and amount_paid_paise != gst.total_paise:
        logger.warning(
            "%s payment %s was %s paise but the invoice total is %s paise; check that the "
            "charged amount includes GST",
            payment_provider,
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
            payment_id=payment_id,
            payment_provider=payment_provider,
            razorpay_invoice_id=razorpay_invoice_id,
            seller=seller_snapshot(),
            buyer=buyer,
        )
    return invoice, True
