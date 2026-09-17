"""Plan entitlements: the one place other apps ask what a workspace's plan allows.

Signatures and keys are frozen by docs/contracts/wave-2.md. Unknown keys raise ``ValueError`` so
typos fail fast.

Semantics by subscription status:

- ``trialing``, ``active`` and ``pending``: the plan's limits and features (``pending`` covers
  an open checkout during the trial and Razorpay's payment-retry grace period).
- ``halted``, ``cancelled`` and ``expired``: a restricted baseline. Every feature is off and each
  limit equals current usage, so existing data stays but nothing new can be added.

Limits are compared with live counts of the underlying rows (see ``services.usage_count``).
``record_usage`` writes an idempotent ledger; it doesn't change those counts.

The plan lookup is memoised on the workspace instance for a few seconds (no global cache), so a
request or task asking repeatedly costs one query; usage counts are always live.
"""

import time
from collections.abc import Mapping
from dataclasses import dataclass

from common.exceptions import Conflict

# Metrics with a per-plan limit (PlanLimits / UsageMetric keys).
WHATSAPP_NUMBERS = "whatsapp_numbers"
MEMBERS = "members"
CONTACTS = "contacts"
METRICS = (WHATSAPP_NUMBERS, MEMBERS, CONTACTS)

# Features a plan may include (Plan.features values).
SCHEDULED_CAMPAIGNS = "scheduled_campaigns"
KEYWORD_AUTOMATIONS = "keyword_automations"
API_ACCESS = "api_access"
COMMERCE = "commerce"  # the WhatsApp store (catalog, carts, orders); on every plan
ANALYTICS = "analytics"  # reports under /api/v1/analytics/; Growth and Pro
FEATURES = (SCHEDULED_CAMPAIGNS, KEYWORD_AUTOMATIONS, API_ACCESS, COMMERCE, ANALYTICS)

ENTITLED_STATUSES = frozenset({"trialing", "active", "pending"})
RESTRICTED_STATUSES = frozenset({"halted", "cancelled", "expired"})

MEMO_SECONDS = 5.0
_MEMO_ATTR = "_billing_entitlements"

_METRIC_LABELS = {
    WHATSAPP_NUMBERS: "WhatsApp numbers",
    MEMBERS: "team members",
    CONTACTS: "contacts",
}


class QuotaExceeded(Conflict):
    """409 ``quota_exceeded``. Raised with ``metric``/``limit``/``used``, the error envelope's
    ``details`` is ``{"metric", "limit", "used"}`` (numbers stay numbers)."""

    default_code = "quota_exceeded"
    default_detail = "Your plan's limit has been reached. Upgrade your plan to add more."

    def __init__(
        self,
        detail=None,
        code=None,
        *,
        metric: str | None = None,
        limit: int | None = None,
        used: int | None = None,
    ) -> None:
        self.metric, self.limit, self.used = metric, limit, used
        if metric is None:
            super().__init__(detail, code)
            return
        message = str(detail) if detail is not None else _quota_message(metric, limit, used)
        super().__init__(message, code)
        # common.exceptions builds the envelope from ``default_detail`` (message) and a dict
        # ``detail`` (details); set both on the instance so the details keep their int values.
        self.default_detail = message
        self.detail = {"metric": metric, "limit": limit, "used": used}

    def __str__(self) -> str:
        return str(self.default_detail) if self.metric is not None else super().__str__()

    def get_codes(self):
        return self.default_code if self.metric is not None else super().get_codes()

    def get_full_details(self):
        if self.metric is None:
            return super().get_full_details()
        return {"message": str(self.default_detail), "code": self.default_code}


def _quota_message(metric: str, limit: int | None, used: int | None) -> str:
    label = _METRIC_LABELS.get(metric, metric.replace("_", " "))
    return (
        f"Your plan allows {limit} {label} and this workspace has {used}. "
        "Upgrade your plan to add more."
    )


@dataclass(frozen=True, slots=True)
class Entitlements:
    status: str
    plan_slug: str
    restricted: bool
    limits: Mapping[str, int | None]
    features: frozenset[str]
    expires_at: float


def _check_metric(metric: str) -> None:
    if metric not in METRICS:
        raise ValueError(f"Unknown entitlement metric {metric!r}; expected one of {METRICS}.")


def _check_feature(feature: str) -> None:
    if feature not in FEATURES:
        raise ValueError(f"Unknown plan feature {feature!r}; expected one of {FEATURES}.")


def get_entitlements(workspace) -> Entitlements:
    """The workspace's plan limits and features for its current status (memoised briefly)."""
    memo = getattr(workspace, _MEMO_ATTR, None)
    if memo is not None and memo.expires_at > time.monotonic():
        return memo

    from . import services

    subscription = services.get_subscription(workspace)
    plan = subscription.plan
    restricted = subscription.status not in ENTITLED_STATUSES
    features = frozenset() if restricted else frozenset(f for f in plan.features if f in FEATURES)
    memo = Entitlements(
        status=subscription.status,
        plan_slug=plan.slug,
        restricted=restricted,
        limits={metric: plan.limit(metric) for metric in METRICS},
        features=features,
        expires_at=time.monotonic() + MEMO_SECONDS,
    )
    setattr(workspace, _MEMO_ATTR, memo)
    return memo


def clear_cache(workspace) -> None:
    """Drop the memoised entitlements after the subscription changes."""
    workspace.__dict__.pop(_MEMO_ATTR, None)


def effective_limit(workspace, metric: str, used: int) -> int | None:
    """The limit that applies now: the plan's, or ``used`` when the subscription is restricted."""
    _check_metric(metric)
    entitlements = get_entitlements(workspace)
    return used if entitlements.restricted else entitlements.limits[metric]


def _usage(workspace, metric: str) -> int:
    from . import services

    return services.usage_count(workspace, metric)


def has_feature(workspace, feature: str) -> bool:
    """Whether the workspace's plan includes ``feature``."""
    _check_feature(feature)
    return feature in get_entitlements(workspace).features


def remaining_quota(workspace, metric: str) -> int | None:
    """Units of ``metric`` the workspace can still add; ``None`` means unlimited."""
    _check_metric(metric)
    entitlements = get_entitlements(workspace)
    if entitlements.restricted:
        return 0
    limit = entitlements.limits[metric]
    if limit is None:
        return None
    return max(limit - _usage(workspace, metric), 0)


def check_quota(workspace, metric: str, amount: int = 1) -> None:
    """Raise :class:`QuotaExceeded` (409 ``quota_exceeded``) if ``amount`` more would exceed it."""
    _check_metric(metric)
    entitlements = get_entitlements(workspace)
    limit = None if entitlements.restricted else entitlements.limits[metric]
    if amount <= 0 or (limit is None and not entitlements.restricted):
        return
    used = _usage(workspace, metric)
    if entitlements.restricted:
        label = _METRIC_LABELS[metric]
        raise QuotaExceeded(
            f"This workspace's subscription is {entitlements.status}. "
            f"Choose a plan to add more {label}.",
            metric=metric,
            limit=used,
            used=used,
        )
    if used + amount > limit:
        raise QuotaExceeded(metric=metric, limit=limit, used=used)


def record_usage(workspace, metric: str, amount: int, *, key: str) -> None:
    """Record ``amount`` units of ``metric``. Idempotent on ``key``: repeats are ignored."""
    _check_metric(metric)
    if not key:
        raise ValueError("record_usage needs a non-empty idempotency key.")
    if len(key) > 255:
        raise ValueError("record_usage keys are limited to 255 characters.")
    from .models import UsageRecord

    UsageRecord.objects.bulk_create(
        [UsageRecord(workspace=workspace, metric=metric, amount=amount, key=key)],
        ignore_conflicts=True,
    )
