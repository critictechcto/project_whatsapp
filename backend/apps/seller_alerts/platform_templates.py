"""Create the seller alert templates in UpChatz's WABA (``manage.py sync_platform_templates``)."""

import logging
from dataclasses import dataclass

from django.conf import settings

from apps.message_templates import validators

from .content import PLATFORM_TEMPLATES, PlatformTemplate
from .platform import platform_client

logger = logging.getLogger(__name__)

PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class TemplateSyncResult:
    name: str
    language: str
    status: str  # Meta's status: APPROVED, PENDING, REJECTED, ...
    category: str
    action: str  # created | unchanged | outdated
    note: str = ""


def _existing_templates(client, waba_id: str) -> dict[tuple[str, str], dict]:
    wanted = {(template.name, template.language) for template in PLATFORM_TEMPLATES}
    found: dict[tuple[str, str], dict] = {}
    after = None
    while True:
        page = client.list_templates(waba_id, after=after, limit=PAGE_SIZE)
        for item in page.get("data") or []:
            key = (item.get("name"), item.get("language"))
            if key in wanted:
                found[key] = item
        paging = page.get("paging") or {}
        after = (paging.get("cursors") or {}).get("after")
        if not paging.get("next") or not after:
            return found


def sync_platform_templates(
    templates: tuple[PlatformTemplate, ...] = PLATFORM_TEMPLATES,
) -> list[TemplateSyncResult]:
    """Create any missing platform template and report the status of every one. Idempotent.

    The Graph client has no template edit call, so a template that differs from its definition
    is reported as ``outdated`` rather than changed. Graph errors propagate.
    """
    waba_id = settings.PLATFORM_WA_WABA_ID
    client = platform_client()
    existing = _existing_templates(client, waba_id)
    results = []
    for template in templates:
        item = existing.get((template.name, template.language))
        if item is None:
            definition = template.definition()
            validators.validate_template(**definition)
            response = client.create_template(waba_id, definition)
            logger.info("Created platform template %s", template.name)
            results.append(
                TemplateSyncResult(
                    name=template.name,
                    language=template.language,
                    status=str(response.get("status") or "PENDING").upper(),
                    category=str(response.get("category") or template.category).upper(),
                    action="created",
                )
            )
            continue
        matches = template.matches(item.get("components"))
        results.append(
            TemplateSyncResult(
                name=template.name,
                language=template.language,
                status=str(item.get("status") or "UNKNOWN").upper(),
                category=str(item.get("category") or "").upper(),
                action="unchanged" if matches else "outdated",
                note=""
                if matches
                else "differs from the definition; edit it in WhatsApp Manager to match",
            )
        )
    return results
