from django.db import models


class Role(models.TextChoices):
    OWNER = "owner", "Owner"
    ADMIN = "admin", "Admin"
    AGENT = "agent", "Agent"
    VIEWER = "viewer", "Viewer"


ROLE_RANK = {Role.OWNER: 40, Role.ADMIN: 30, Role.AGENT: 20, Role.VIEWER: 10}


def role_at_least(role: str, minimum: str) -> bool:
    """True when ``role`` is ``minimum`` or higher (owner > admin > agent > viewer)."""
    return ROLE_RANK.get(role, 0) >= ROLE_RANK[minimum]
