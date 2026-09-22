"""Contact and consent operations shared by the API, the import task and signal receivers."""

import string
from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from common.phone import InvalidPhoneNumber, normalize_e164, to_wa_id

from .models import ConsentEvent, ConsentKeywords, Contact, default_opt_in_keywords

# Always opt out, whatever the workspace configures: customers expect STOP to work.
LOCKED_OPT_OUT_KEYWORDS = frozenset({"stop", "unsubscribe", "stop promotions", "stop all"})
OPT_OUT_KEYWORDS = LOCKED_OPT_OUT_KEYWORDS
# The default opt-in words; a workspace may replace them.
OPT_IN_KEYWORDS = frozenset(default_opt_in_keywords())
MAX_KEYWORD_LENGTH = 40
MAX_KEYWORDS_PER_LIST = 20
_TRAILING_PUNCTUATION = string.punctuation + "।"


def wa_id_to_e164(wa_id: str) -> str:
    """E.164 for a WhatsApp id. Meta's ids are authoritative, so digits-only ids that the phone
    metadata doesn't know yet are still accepted."""
    try:
        return normalize_e164(wa_id)
    except InvalidPhoneNumber:
        digits = str(wa_id or "").strip()
        if digits.isdigit() and 8 <= len(digits) <= 15 and not digits.startswith("0"):
            return f"+{digits}"
        raise


def get_or_create_from_wa(workspace, wa_id: str, profile_name: str | None = None) -> Contact:
    """Contact for a WhatsApp id in ``workspace``; fills a blank name from ``profile_name``."""
    phone = wa_id_to_e164(wa_id)
    profile_name = (profile_name or "").strip()[:255]
    contact, created = Contact.objects.get_or_create(
        workspace=workspace,
        phone_e164=phone,
        defaults={"wa_id": to_wa_id(phone), "name": profile_name},
    )
    if not created and profile_name and not contact.name:
        updated = Contact.objects.filter(pk=contact.pk, name="").update(
            name=profile_name, updated_at=timezone.now()
        )
        if updated:
            contact.name = profile_name
    return contact


def touch_last_inbound(contact: Contact, timestamp: datetime) -> None:
    """Set ``last_inbound_at`` to ``timestamp`` unless a later message was already seen."""
    updated = Contact.objects.filter(
        Q(last_inbound_at__isnull=True) | Q(last_inbound_at__lt=timestamp), pk=contact.pk
    ).update(last_inbound_at=timestamp, updated_at=timezone.now())
    if updated:
        contact.last_inbound_at = timestamp


def record_opt_in(
    contact: Contact,
    *,
    source: str,
    actor=None,
    evidence: str = "",
    wamid: str = "",
    occurred_at: datetime | None = None,
) -> ConsentEvent | None:
    """Opt ``contact`` in to marketing. Returns the new event, or None when nothing changed."""
    return _record_consent(
        contact,
        ConsentEvent.Action.OPT_IN,
        source=source,
        actor=actor,
        evidence=evidence,
        wamid=wamid,
        occurred_at=occurred_at,
    )


def record_opt_out(
    contact: Contact,
    *,
    source: str,
    actor=None,
    evidence: str = "",
    wamid: str = "",
    occurred_at: datetime | None = None,
) -> ConsentEvent | None:
    """Opt ``contact`` out of marketing. Returns the new event, or None when nothing changed."""
    return _record_consent(
        contact,
        ConsentEvent.Action.OPT_OUT,
        source=source,
        actor=actor,
        evidence=evidence,
        wamid=wamid,
        occurred_at=occurred_at,
    )


def _record_consent(
    contact: Contact,
    action: str,
    *,
    source: str,
    actor,
    evidence: str,
    wamid: str,
    occurred_at: datetime | None,
) -> ConsentEvent | None:
    event = None
    with transaction.atomic():
        locked = Contact.objects.select_for_update().get(pk=contact.pk)
        already_seen = wamid and ConsentEvent.objects.filter(contact=locked, wamid=wamid).exists()
        target = (
            Contact.OptInStatus.OPTED_IN
            if action == ConsentEvent.Action.OPT_IN
            else Contact.OptInStatus.OPTED_OUT
        )
        if not already_seen and locked.marketing_opt_in_status != target:
            occurred_at = occurred_at or timezone.now()
            locked.marketing_opt_in_status = target
            update_fields = ["marketing_opt_in_status", "updated_at"]
            if target == Contact.OptInStatus.OPTED_IN:
                locked.opted_in_at = occurred_at
                locked.opt_in_source = source
                update_fields += ["opted_in_at", "opt_in_source"]
            else:
                locked.opted_out_at = occurred_at
                update_fields.append("opted_out_at")
            locked.save(update_fields=update_fields)
            event = ConsentEvent.objects.create(
                workspace_id=locked.workspace_id,
                contact=locked,
                action=action,
                source=source,
                evidence=evidence,
                actor=actor,
                wamid=wamid or "",
                occurred_at=occurred_at,
            )
    for field in ("marketing_opt_in_status", "opted_in_at", "opted_out_at", "opt_in_source"):
        setattr(contact, field, getattr(locked, field))
    return event


def is_marketing_allowed(contact: Contact) -> bool:
    """Marketing templates may only go to contacts with a recorded opt-in."""
    return contact.marketing_opt_in_status == Contact.OptInStatus.OPTED_IN


def normalize_keyword(text: str | None) -> str:
    """How keyword messages and configured words are compared: case, spacing and trailing
    punctuation are ignored."""
    return " ".join((text or "").split()).casefold().rstrip(_TRAILING_PUNCTUATION).strip()


@dataclass(frozen=True, slots=True)
class KeywordSets:
    opt_in: frozenset[str]
    opt_out: frozenset[str]


DEFAULT_KEYWORDS = KeywordSets(opt_in=OPT_IN_KEYWORDS, opt_out=LOCKED_OPT_OUT_KEYWORDS)


def consent_keywords(workspace_id) -> KeywordSets:
    """The workspace's consent words; the locked opt-out words always apply."""
    settings_row = (
        ConsentKeywords.objects.filter(workspace_id=workspace_id)
        .values("opt_in_keywords", "opt_out_keywords")
        .first()
    )
    if settings_row is None:
        return DEFAULT_KEYWORDS
    return KeywordSets(
        opt_in=frozenset(settings_row["opt_in_keywords"] or ()),
        opt_out=LOCKED_OPT_OUT_KEYWORDS | frozenset(settings_row["opt_out_keywords"] or ()),
    )


def match_consent_keyword(text: str | None, keywords: KeywordSets = DEFAULT_KEYWORDS) -> str | None:
    """``ConsentEvent.Action`` for an exact opt-in/opt-out keyword message, else None. Opt-out
    wins if a word is somehow in both sets."""
    normalized = normalize_keyword(text)
    if not normalized:
        return None
    if normalized in keywords.opt_out:
        return ConsentEvent.Action.OPT_OUT
    if normalized in keywords.opt_in:
        return ConsentEvent.Action.OPT_IN
    return None


def match_workspace_consent_keyword(workspace_id, text: str | None) -> str | None:
    """``match_consent_keyword`` with the workspace's words (loaded only for short messages)."""
    normalized = normalize_keyword(text)
    if not normalized or len(normalized) > MAX_KEYWORD_LENGTH:
        return None
    return match_consent_keyword(normalized, consent_keywords(workspace_id))


def _same_workspace_tags(contact: Contact, tags) -> list:
    tags = list(tags)
    if any(tag.workspace_id != contact.workspace_id for tag in tags):
        raise ValueError("Tags must belong to the contact's workspace.")
    return tags


def add_tags(contact: Contact, tags) -> None:
    """Attach ``tags`` (same workspace) to ``contact``; already-attached tags are ignored."""
    contact.tags.add(*_same_workspace_tags(contact, tags))


def remove_tags(contact: Contact, tags) -> None:
    contact.tags.remove(*_same_workspace_tags(contact, tags))
