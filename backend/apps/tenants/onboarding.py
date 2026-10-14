"""Per-person onboarding state for a workspace (docs/contracts/onboarding.md)."""

from django.utils import timezone

from .models import Membership, Workspace

# API flag -> Membership timestamp field.
FLAG_FIELDS = {
    "welcome_completed": "welcome_completed_at",
    "tour_completed": "tour_completed_at",
    "checklist_dismissed": "checklist_dismissed_at",
}


def update_onboarding(
    membership: Membership, *, goals: list[str] | None = None, **flags: bool
) -> None:
    """Set the workspace goals and the caller's flags: true stamps now, false clears."""
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
    if goals is not None:
        ordered = [goal for goal in Workspace.Goal.values if goal in goals]
        if ordered != workspace.business_goals:
            workspace.business_goals = ordered
            workspace.save(update_fields=["business_goals", "updated_at"])
