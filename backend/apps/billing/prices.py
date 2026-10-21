"""Plan prices, read from Razorpay plans (docs/contracts/billing-razorpay.md, "Prices come from
Razorpay plans").

Razorpay is the only source of plan prices. Each ``Plan`` names a Razorpay plan per interval
(``Plan.razorpay_plan_id``); its amount is fetched once with ``GET /v1/plans/{id}`` and kept as a
``RazorpayPlan`` copy. A Razorpay plan can't change after it is created, so the copy never goes
stale. A failed fetch is remembered in the cache for :data:`FAILURE_TTL_SECONDS`, so anonymous
traffic (the public plans endpoint) can't hammer Razorpay.

The Razorpay amount is what is charged per cycle: GST-inclusive when GST is on. The price shown
and invoiced "before GST" is worked back from it (:func:`price_paise`).
"""

import logging
from collections.abc import Iterable
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction

from common.razorpay import checked_id

from . import invoices, razorpay
from .models import Plan, RazorpayPlan
from .razorpay import RazorpayError

logger = logging.getLogger(__name__)

FAILURE_TTL_SECONDS = 60
CURRENCY = "INR"
# Razorpay (period, interval) pairs accepted for each UpChatz billing interval.
ACCEPTED_PERIODS = {
    "monthly": frozenset({("monthly", 1)}),
    "annual": frozenset({("yearly", 1), ("monthly", 12)}),
}
_NOT_FOUND = "not_found"
_INVALID = "invalid"
_UNREACHABLE = "unreachable"
_PREFETCH_ATTR = "_razorpay_plan_cache"


class PlanPriceNotConfigured(Exception):
    """The interval has no Razorpay plan, or the plan doesn't exist or doesn't fit."""


class RazorpayPlanNotFound(PlanPriceNotConfigured):
    """Razorpay has no plan with that id (for example a test-mode id with live keys)."""


def gst_rate_percent() -> int:
    """The GST rate charged on plans: 0 while ``BILLING_GST_ENABLED`` is off (not registered)."""
    return settings.BILLING_GST_RATE_PERCENT if settings.BILLING_GST_ENABLED else 0


def _failure_key(plan_id: str) -> str:
    return f"billing:razorpay-plan-failure:{plan_id}"


def check_fits(*, period: object, period_interval: object, currency: object, interval: str) -> None:
    """Raise :class:`PlanPriceNotConfigured` unless a Razorpay plan can bill ``interval``:
    INR, and monthly x 1 for monthly; yearly x 1 or monthly x 12 for annual."""
    if currency != CURRENCY:
        raise PlanPriceNotConfigured(f"The Razorpay plan is in {currency}, not {CURRENCY}.")
    if (period, period_interval) not in ACCEPTED_PERIODS.get(interval, frozenset()):
        expected = "every month" if interval == "monthly" else "every year (or 12 months)"
        raise PlanPriceNotConfigured(
            f"The Razorpay plan bills every {period_interval} {period}; {interval} needs one "
            f"that bills {expected}."
        )


def parse_plan_entity(plan_id: str, entity: Any) -> dict:
    """``RazorpayPlan`` field values from a Razorpay plan entity, or ``PlanPriceNotConfigured``."""
    item = entity.get("item") if isinstance(entity, dict) else None
    if not isinstance(item, dict) or entity.get("id") != plan_id:
        raise PlanPriceNotConfigured("Razorpay returned an unexpected plan.")
    amount = item.get("amount")
    period_interval = entity.get("interval")
    valid = (
        isinstance(amount, int)
        and not isinstance(amount, bool)
        and amount > 0
        and isinstance(period_interval, int)
        and not isinstance(period_interval, bool)
        and period_interval > 0
        and isinstance(entity.get("period"), str)
    )
    if not valid:
        raise PlanPriceNotConfigured("Razorpay returned a plan without a usable amount or period.")
    return {
        "period": entity["period"][:16],
        "period_interval": period_interval,
        "amount_paise": amount,
        "currency": str(item.get("currency") or "")[:3],
        "item_name": str(item.get("name") or "")[:255],
    }


def fetch_plan(plan_id: str, *, use_cache: bool = True) -> dict:
    """Razorpay's plan as ``RazorpayPlan`` field values. Raises ``PlanPriceNotConfigured`` when
    it doesn't exist (Razorpay answers 400 or 404) and ``RazorpayError`` when Razorpay can't be
    reached; either failure is remembered for :data:`FAILURE_TTL_SECONDS` (skipped with
    ``use_cache=False``)."""
    try:
        checked_id(plan_id, label="Razorpay plan id")
    except RazorpayError:
        raise RazorpayPlanNotFound("That isn't a valid Razorpay plan id.") from None
    key = _failure_key(plan_id)
    if use_cache:
        failure = cache.get(key)
        if failure == _NOT_FOUND:
            raise RazorpayPlanNotFound("The Razorpay plan wasn't found.")
        if failure == _INVALID:
            raise PlanPriceNotConfigured("Razorpay returned an unusable plan a moment ago.")
        if failure == _UNREACHABLE:
            raise RazorpayError("Razorpay was unreachable a moment ago.")
    try:
        entity = razorpay.get_razorpay_client().fetch_plan(plan_id)
        return parse_plan_entity(plan_id, entity)
    except RazorpayError as exc:
        not_found = exc.status_code in (400, 404)
        cache.set(key, _NOT_FOUND if not_found else _UNREACHABLE, FAILURE_TTL_SECONDS)
        if not_found:
            raise RazorpayPlanNotFound("The Razorpay plan wasn't found.") from exc
        logger.warning("Could not fetch Razorpay plan %s: %s", plan_id, exc)
        raise
    except PlanPriceNotConfigured:
        cache.set(key, _INVALID, FAILURE_TTL_SECONDS)
        raise


def store_snapshot(plan_id: str, fields: dict, *, plan: Plan | None, interval: str) -> RazorpayPlan:
    """Save the copy of a fetched plan (or return the one a concurrent request saved)."""
    try:
        with transaction.atomic():
            snapshot, _ = RazorpayPlan.objects.get_or_create(
                pk=plan_id,
                defaults={
                    **fields,
                    "plan": plan if plan and plan.pk else None,
                    "interval": interval,
                },
            )
    except IntegrityError:  # pragma: no cover - lost a race; the other request saved it
        snapshot = RazorpayPlan.objects.get(pk=plan_id)
    return snapshot


def _prefetched(plan: Plan) -> dict[str, RazorpayPlan] | None:
    return getattr(plan, _PREFETCH_ATTR, None)


def prefetch(plans: Iterable[Plan]) -> list[Plan]:
    """Load the ``RazorpayPlan`` copies of every plan's ids in one query, so pricing a list of
    plans doesn't query once per plan and interval. Returns the plans as a list."""
    plans = list(plans)
    ids = {
        plan_id
        for plan in plans
        for interval in ACCEPTED_PERIODS
        if (plan_id := plan.razorpay_plan_id(interval))
    }
    found = {snapshot.pk: snapshot for snapshot in RazorpayPlan.objects.filter(pk__in=ids)}
    for plan in plans:
        setattr(plan, _PREFETCH_ATTR, found)
    return plans


def razorpay_plan(plan: Plan, interval: str, *, use_cache: bool = True) -> RazorpayPlan:
    """The ``RazorpayPlan`` copy for the plan's current Razorpay plan id for ``interval``,
    fetched and saved on a miss. Raises ``PlanPriceNotConfigured`` (no id, not found, wrong
    period or currency) or ``RazorpayError`` (unreachable)."""
    plan_id = plan.razorpay_plan_id(interval)
    if not plan_id:
        raise PlanPriceNotConfigured(f"No Razorpay plan is set for {plan.slug} ({interval}).")
    known = _prefetched(plan)
    snapshot = known.get(plan_id) if known is not None else None
    if snapshot is None:
        snapshot = RazorpayPlan.objects.filter(pk=plan_id).first()
    if snapshot is None:
        # Saved even when it doesn't fit (checked below), so a misfit isn't fetched again.
        fields = fetch_plan(plan_id, use_cache=use_cache)
        snapshot = store_snapshot(plan_id, fields, plan=plan, interval=interval)
    if known is not None:
        known[plan_id] = snapshot
    check_fits(
        period=snapshot.period,
        period_interval=snapshot.period_interval,
        currency=snapshot.currency,
        interval=interval,
    )
    return snapshot


def check_plan_id(plan_id: str, interval: str) -> dict:
    """Validate a Razorpay plan id for ``interval`` (the admin form): the saved copy, else a
    fresh fetch that skips the failure cache. Returns ``RazorpayPlan`` field values; raises
    ``PlanPriceNotConfigured`` or ``RazorpayError``."""
    snapshot = RazorpayPlan.objects.filter(pk=plan_id).first()
    if snapshot is not None:
        fields = {
            "period": snapshot.period,
            "period_interval": snapshot.period_interval,
            "amount_paise": snapshot.amount_paise,
            "currency": snapshot.currency,
            "item_name": snapshot.item_name,
        }
    else:
        fields = fetch_plan(plan_id, use_cache=False)
    check_fits(
        period=fields["period"],
        period_interval=fields["period_interval"],
        currency=fields["currency"],
        interval=interval,
    )
    cache.delete(_failure_key(plan_id))
    return fields


def assign(plan: Plan, interval: str, plan_id: str, fields: dict) -> RazorpayPlan:
    """Save the copy of a validated Razorpay plan and record that ``plan`` uses it for
    ``interval`` (an id reused from another plan is re-pointed)."""
    snapshot = store_snapshot(plan_id, fields, plan=plan, interval=interval)
    if snapshot.plan_id != plan.pk or snapshot.interval != interval:
        snapshot.plan = plan
        snapshot.interval = interval
        snapshot.save(update_fields=["plan", "interval"])
    return snapshot


def base_price_paise(amount_paise: int) -> int:
    """The price before GST of a GST-inclusive Razorpay amount at the current GST rate: the base
    whose ``invoices.compute_gst`` total equals it (the amount itself with GST off)."""
    seller = settings.BILLING_SELLER_STATE_CODE
    return invoices.subtotal_for_total(
        amount_paise,
        buyer_state_code=seller,
        seller_state_code=seller,
        rate_percent=gst_rate_percent(),
    )


def price_paise(plan: Plan, interval: str) -> int | None:
    """The plan's price before GST for ``interval``, or None when it can't be bought right now
    (no Razorpay plan, a plan that doesn't fit, or Razorpay unreachable with nothing saved).
    Never raises."""
    try:
        snapshot = razorpay_plan(plan, interval)
    except (PlanPriceNotConfigured, RazorpayError):
        return None
    return base_price_paise(snapshot.amount_paise)
