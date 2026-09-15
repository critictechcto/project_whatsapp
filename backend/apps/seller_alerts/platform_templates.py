"""Create and update the seller alert templates in UpChatz's WABA
(``manage.py sync_platform_templates``)."""

import logging
from dataclasses import dataclass

from django.conf import settings

from apps.message_templates import validators
from apps.whatsapp.client.errors import GraphAPIError, GraphPermissionError, TokenInvalidError

from .content import PLATFORM_TEMPLATES, PlatformTemplate
from .platform import platform_client

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
# Meta only allows edits in these statuses; an APPROVED template's category can't change.
EDITABLE_STATUSES = frozenset({"APPROVED", "REJECTED", "PAUSED"})


@dataclass(frozen=True, slots=True)
class TemplateSyncResult:
    name: str
    language: str
    status: str  # Meta's status: APPROVED, PENDING, REJECTED, ...
    category: str
    action: str  # created | unchanged | updated | outdated
    note: str = ""  # for outdated: why the template couldn't be updated


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


def _update(client, template: PlatformTemplate, item: dict) -> TemplateSyncResult:
    """Edit Meta's copy to match the definition when Meta allows it."""
    status = str(item.get("status") or "UNKNOWN").upper()
    category = str(item.get("category") or "").upper()

    def result(action: str, note: str = "", new_status: str = status) -> TemplateSyncResult:
        return TemplateSyncResult(
            name=template.name,
            language=template.language,
            status=new_status,
            category=category,
            action=action,
            note=note,
        )

    if status not in EDITABLE_STATUSES:
        return result("outdated", f"Meta doesn't allow edits while the template is {status}")
    definition = template.definition()
    validators.validate_template(**definition)
    # The category of an approved template can't be edited; send it only when it may change.
    new_category = (
        template.category if status != "APPROVED" and category != template.category else None
    )
    try:
        client.edit_message_template(
            str(item["id"]), components=definition["components"], category=new_category
        )
    except (TokenInvalidError, GraphPermissionError):
        raise
    except GraphAPIError as exc:
        if exc.retryable:
            raise
        logger.warning("Meta refused to edit platform template %s: %s", template.name, exc)
        return result("outdated", f"Meta refused the edit: {exc.message or exc}")
    logger.info("Updated platform template %s", template.name)
    if new_category:
        category = new_category
    # Meta re-reviews edits: a rejected template goes back to review, approved and paused ones
    # are re-approved unless the review fails.
    return result("updated", new_status="PENDING" if status == "REJECTED" else status)


def sync_platform_templates(
    templates: tuple[PlatformTemplate, ...] = PLATFORM_TEMPLATES,
) -> list[TemplateSyncResult]:
    """Create missing platform templates, edit the ones that differ from their definition where
    Meta allows it, and report the status of every one. Idempotent.

    A template Meta won't let us edit (its status, or the edit limit on approved templates) is
    reported as ``outdated`` with the reason. Other Graph errors propagate.
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
        elif template.matches(item.get("components")):
            results.append(
                TemplateSyncResult(
                    name=template.name,
                    language=template.language,
                    status=str(item.get("status") or "UNKNOWN").upper(),
                    category=str(item.get("category") or "").upper(),
                    action="unchanged",
                )
            )
        else:
            results.append(_update(client, template, item))
    return results
