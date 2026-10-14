"""Per-person onboarding state for a workspace (docs/contracts/onboarding.md)."""

from django.utils import timezone

from .models import Membership

# API flag -> Membership timestamp field.
FLAG_FIELDS = {
    "welcome_completed": "welcome_completed_at",
    "tour_completed": "tour_completed_at",
    "checklist_dismissed": "checklist_dismissed_at",
}


def update_onboarding(membership: Membership, *, goal: str | None = None, **flags: bool) -> None:
    """Set the workspace goal and the caller's flags: true stamps now, false clears."""
    now = timezone.now()
    changed = []
    for flag, value in flags.items():
        field = FLAG_FIELDS[flag]
        current = getattr(membership, field)
        if value and current is None:
            setattr(membership, field, now)
            changed.append(field)
        elif not value and current is not None:
            setattr(membership, field, None)
            changed.append(field)
    if changed:
        membership.save(update_fields=[*changed, "updated_at"])
    workspace = membership.workspace
    if goal is not None and goal != workspace.business_goal:
        workspace.business_goal = goal
        workspace.save(update_fields=["business_goal", "updated_at"])
