"""Plan entitlements: the one place other apps ask what a workspace's plan allows.

Signatures and keys are frozen by docs/contracts/wave-2.md. Until billing models exist these are
allow-all stubs: every feature is on, quotas are unlimited and usage isn't recorded. Unknown keys
raise ``ValueError`` so typos fail fast.
"""

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
FEATURES = (SCHEDULED_CAMPAIGNS, KEYWORD_AUTOMATIONS, API_ACCESS)


class QuotaExceeded(Conflict):
    default_code = "quota_exceeded"
    default_detail = "Your plan's limit has been reached. Upgrade your plan to add more."


def _check_metric(metric: str) -> None:
    if metric not in METRICS:
        raise ValueError(f"Unknown entitlement metric {metric!r}; expected one of {METRICS}.")


def _check_feature(feature: str) -> None:
    if feature not in FEATURES:
        raise ValueError(f"Unknown plan feature {feature!r}; expected one of {FEATURES}.")


def has_feature(workspace, feature: str) -> bool:
    """Whether the workspace's plan includes ``feature``."""
    _check_feature(feature)
    return True


def remaining_quota(workspace, metric: str) -> int | None:
    """Units of ``metric`` the workspace can still add; ``None`` means unlimited."""
    _check_metric(metric)
    return None


def check_quota(workspace, metric: str, amount: int = 1) -> None:
    """Raise :class:`QuotaExceeded` (409 ``quota_exceeded``) if ``amount`` more would exceed it."""
    remaining = remaining_quota(workspace, metric)
    if remaining is not None and amount > remaining:
        raise QuotaExceeded(
            f"Your plan allows {max(remaining, 0)} more {metric.replace('_', ' ')}. "
            "Upgrade your plan to add more."
        )


def record_usage(workspace, metric: str, amount: int, *, key: str) -> None:
    """Record ``amount`` units of ``metric``. Idempotent on ``key``: repeats are ignored."""
    _check_metric(metric)
    if not key:
        raise ValueError("record_usage needs a non-empty idempotency key.")
