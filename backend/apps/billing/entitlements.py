"""Plan entitlements. Stub until billing is built: everything is allowed, no quotas.

Other apps call these instead of reading plan data directly, so enforcement lands in one place.
"""


def has_feature(workspace, feature: str) -> bool:
    return True


def remaining_quota(workspace, metric: str) -> int | None:
    """Remaining units of ``metric`` this billing period; None means unlimited."""
    return None
