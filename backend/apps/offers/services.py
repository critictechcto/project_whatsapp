"""Offers services (docs/contracts/services-and-offers.md): the import surface for other apps.

Other apps use ``match_code``, ``apply_to_checkout``, ``release_for_order`` and
``AppliedOffer``. The rest (inbound code handling, the order lifecycle, counter redemption and
stats) is used by this app's receivers, tasks and views.
"""

from __future__ import annotations

import logging
import re
import string
import uuid
from dataclasses import dataclass
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.billing import entitlements
from apps.contacts import services as contact_services
from apps.contacts.models import Contact
from apps.inbox import sending
from apps.inbox.interactive import InvalidInteractiveContent, reply_buttons
from apps.inbox.models import Message
from apps.orders.models import DEFAULT_MENU_KEYWORDS, StoreSettings
from apps.tenants.models import Workspace
from common.commerce import build_reply_id
from common.exceptions import Conflict
from common.phone import InvalidPhoneNumber, normalize_e164

from .models import OfferClaim, OfferCode

logger = logging.getLogger(__name__)

# Stripped from both ends of a message, so "Diwali!" matches DIWALI (as automations' exact mode).
EDGE_PUNCTUATION = string.punctuation + "".join(
    map(chr, (0x0964, 0x0965, 0xBF, 0xA1, 0x2026, 0x201C, 0x201D, 0x2018, 0x2019))
)  # danda, double danda, inverted ? and !, ellipsis, curly quotes
_CODE_TEXT_RE = re.compile(r"^[a-z0-9_-]{2,20}$")
MAX_MATCH_TEXT = 40
MIN_PAYABLE_PAISE = 100  # a discount never brings the amount to pay below ₹1
STATS_DAYS = 30

CLAIMED = OfferClaim.Status.CLAIMED
APPLIED = OfferClaim.Status.APPLIED
REDEEMED = OfferClaim.Status.REDEEMED
EXPIRED = OfferClaim.Status.EXPIRED
USED_STATUSES = (APPLIED, REDEEMED)  # what max_uses counts

SOURCE_REF_PREFIX = "offer:"
SHOP_NOW, BOOK_NOW, MENU = "Shop now", "Book now", "Menu"
FULLY_CLAIMED_TEXT = "Sorry, this offer has been fully claimed."


@dataclass(frozen=True)
class AppliedOffer:
    claim_id: uuid.UUID
    code: str
    discount_paise: int


class OfferUnavailable(Conflict):
    default_code = "offer_unavailable"
    default_detail = "This offer is not available: it is inactive, out of dates or fully used."


class OfferInUse(Conflict):
    default_code = "offer_in_use"
    default_detail = "This offer has claims and cannot be deleted. Deactivate it instead."


class InvalidClaimTransition(Conflict):
    default_code = "invalid_transition"
    default_detail = "This claim cannot be redeemed in its current status."


# --- Matching -----------------------------------------------------------------------------------


def _candidates(text: str | None) -> list[str]:
    """Upper-case code candidates for a whole message (normalised like automations' exact mode)."""
    message = " ".join(str(text or "").split()).casefold()
    if not message or len(message) > MAX_MATCH_TEXT:
        return []
    found = {message, message.strip(EDGE_PUNCTUATION).strip()}
    return sorted(value.upper() for value in found if _CODE_TEXT_RE.fullmatch(value))


def live_offers(now=None):
    """Active codes within their dates (all workspaces; filter further)."""
    now = now or timezone.now()
    return OfferCode.objects.filter(
        Q(starts_at__isnull=True) | Q(starts_at__lte=now),
        Q(ends_at__isnull=True) | Q(ends_at__gt=now),
        is_active=True,
    )


def is_live(offer: OfferCode, now=None) -> bool:
    now = now or timezone.now()
    return (
        offer.is_active
        and (offer.starts_at is None or offer.starts_at <= now)
        and (offer.ends_at is None or offer.ends_at > now)
    )


def match_code(workspace_id, text: str | None) -> OfferCode | None:
    """The active offer code that ``text`` is exactly, or None.

    Whole-message match after normalisation (trim, casefold, strip edge punctuation); the code
    must be active and within its dates. Cheap for ordinary messages: no query unless the text
    looks like a code.
    """
    candidates = _candidates(text)
    if not candidates or workspace_id is None:
        return None
    return live_offers().filter(workspace_id=workspace_id, code__in=candidates).first()


def _normalize_word(value) -> str:
    return " ".join(str(value or "").split()).casefold().strip(EDGE_PUNCTUATION).strip()


def code_collision(workspace, code: str) -> str | None:
    """Why ``code`` can't be used (it equals a menu, consent or opt-out keyword), or None."""
    word = _normalize_word(code)
    menu_keywords = (
        StoreSettings.objects.filter(workspace=workspace)
        .values_list("menu_keywords", flat=True)
        .first()
    )
    if menu_keywords is None:
        menu_keywords = DEFAULT_MENU_KEYWORDS
    if word in {_normalize_word(keyword) for keyword in menu_keywords or ()}:
        return "This code is a store menu keyword. Choose another code."
    if word in {_normalize_word(k) for k in contact_services.LOCKED_OPT_OUT_KEYWORDS}:
        return "This code is an opt-out keyword. Choose another code."
    keywords = contact_services.consent_keywords(workspace.pk)
    if word in {_normalize_word(k) for k in (*keywords.opt_in, *keywords.opt_out)}:
        return "This code is a consent keyword. Choose another code."
    return None


# --- Discounts and limits ----------------------------------------------------------------------


def discount_for(offer: OfferCode, subtotal_paise: int) -> int:
    """The discount on ``subtotal_paise``: percent floored and capped, amount up to the subtotal
    less ₹1. Never leaves less than ₹1 to pay; 0 for offers without a discount."""
    subtotal = max(int(subtotal_paise or 0), 0)
    if offer.discount_type == OfferCode.DiscountType.PERCENT:
        discount = subtotal * offer.discount_value // 100
        if offer.max_discount_paise is not None:
            discount = min(discount, offer.max_discount_paise)
    elif offer.discount_type == OfferCode.DiscountType.AMOUNT:
        discount = offer.discount_value
    else:
        return 0
    return max(min(discount, subtotal - MIN_PAYABLE_PAISE), 0)


def uses_count(offer: OfferCode, *, exclude_claim_id=None) -> int:
    claims = OfferClaim.objects.filter(offer=offer, status__in=USED_STATUSES)
    if exclude_claim_id is not None:
        claims = claims.exclude(pk=exclude_claim_id)
    return claims.count()


def has_capacity(offer: OfferCode, *, exclude_claim_id=None) -> bool:
    """Whether one more claim may be applied or redeemed (``max_uses``)."""
    return offer.max_uses is None or uses_count(offer, exclude_claim_id=exclude_claim_id) < (
        offer.max_uses
    )


def _applies_to_kind(offer: OfferCode, order_kind: str) -> bool:
    is_booking = order_kind == "booking"
    if offer.applies_to == OfferCode.AppliesTo.PRODUCTS:
        return not is_booking
    if offer.applies_to == OfferCode.AppliesTo.SERVICES:
        return is_booking
    return True


def eligible_subtotal(offer: OfferCode, order) -> int:
    """The part of the order's subtotal the offer counts: every line, or for ``items`` only the
    lines of the chosen catalog items (0 when the order has none of them)."""
    if offer.applies_to != OfferCode.AppliesTo.ITEMS:
        return int(order.subtotal_paise or 0)
    chosen = set(offer.products.values_list("pk", flat=True))
    return sum(
        line.line_total_paise
        for line in order.items.all()
        if line.product_id is not None and line.product_id in chosen
    )


# --- Checkout -----------------------------------------------------------------------------------


def apply_to_checkout(order) -> AppliedOffer | None:
    """Apply the contact's open claim to ``order``; None when no offer applies.

    Takes the claim already applied to this order, else the newest ``claimed`` claim of the
    order's contact that qualifies (live offer, ``applies_to`` vs the order kind, minimum order
    and discount on the eligible subtotal, which for ``items`` is only the chosen items' lines,
    ``max_uses``). A claim applied to this order that no longer qualifies goes back to
    ``claimed``. Never raises for an invalid offer.
    """
    if order is None or getattr(order, "pk", None) is None:
        return None
    order_kind = getattr(order, "kind", "delivery") or "delivery"
    subtotal = int(order.subtotal_paise or 0)
    now = timezone.now()
    with transaction.atomic():
        claims = list(
            OfferClaim.objects.select_for_update(of=("self",))
            .select_related("offer")
            .filter(workspace_id=order.workspace_id, contact_id=order.contact_id)
            .filter(Q(status=CLAIMED) | Q(status=APPLIED, order_id=order.pk))
            .order_by("-created_at")[:20]
        )
        claims.sort(key=lambda claim: claim.status != APPLIED)  # this order's claim first
        for claim in claims:
            offer = OfferCode.objects.select_for_update().get(pk=claim.offer_id)
            eligible = min(eligible_subtotal(offer, order), subtotal)
            discount = discount_for(offer, eligible)
            usable = (
                is_live(offer, now)
                and _applies_to_kind(offer, order_kind)
                and eligible > 0
                and eligible >= offer.min_order_paise
                and (discount > 0 or offer.discount_type == OfferCode.DiscountType.NONE)
                and (claim.status == APPLIED or has_capacity(offer))
            )
            if usable:
                OfferClaim.objects.filter(pk=claim.pk).update(
                    status=APPLIED, order_id=order.pk, discount_paise=discount, updated_at=now
                )
                return AppliedOffer(claim_id=claim.pk, code=offer.code, discount_paise=discount)
            if claim.status == APPLIED:
                _release(OfferClaim.objects.filter(pk=claim.pk), now)
    return None


def _release(claims, now=None) -> int:
    return claims.filter(status=APPLIED).update(
        status=CLAIMED, order=None, discount_paise=0, updated_at=now or timezone.now()
    )


def release_for_order(order) -> None:
    """Put the claim applied to ``order`` back to claimed."""
    if order is None or getattr(order, "pk", None) is None:
        return
    release_for_order_id(order.workspace_id, order.pk)


def release_for_order_id(workspace_id, order_id) -> int:
    return _release(OfferClaim.objects.filter(workspace_id=workspace_id, order_id=order_id))


def redeem_for_order_id(workspace_id, order_id, *, bill_paise: int) -> int:
    """Mark the claims applied to an order redeemed (the order was paid and fulfilled)."""
    now = timezone.now()
    return OfferClaim.objects.filter(
        workspace_id=workspace_id, order_id=order_id, status=APPLIED
    ).update(status=REDEEMED, redeemed_at=now, bill_paise=bill_paise, updated_at=now)


def expire_claims(now=None) -> int:
    """``claimed`` claims of offers past ``ends_at`` (never applied) become ``expired``."""
    now = now or timezone.now()
    return OfferClaim.objects.filter(status=CLAIMED, offer__ends_at__lte=now).update(
        status=EXPIRED, updated_at=now
    )


# --- Inbound codes ------------------------------------------------------------------------------


def commerce_enabled(workspace_id) -> bool:
    workspace = Workspace.objects.filter(pk=workspace_id, is_active=True).first()
    return workspace is not None and entitlements.has_feature(workspace, entitlements.COMMERCE)


def is_offer_message(event) -> bool:
    """Commerce claimer: an inbound text that is exactly a live code of a commerce workspace.
    Read-only and quick (no query unless the text looks like a code)."""
    if event.direction != "inbound" or event.source != "inbound" or event.type != "text":
        return False
    if not _candidates(event.text):
        return False
    return match_code(event.workspace_id, event.text) is not None and commerce_enabled(
        event.workspace_id
    )


def _referral(payload) -> dict[str, str]:
    referral = payload.get("referral") if isinstance(payload, dict) else None
    if not isinstance(referral, dict):
        referral = {}

    def value(key: str, limit: int) -> str:
        raw = referral.get(key)
        return str(raw).strip()[:limit] if isinstance(raw, str | int) else ""

    url = value("source_url", 1000)
    return {
        "ad_source_id": value("source_id", 128),
        "ad_source_url": url if url.startswith(("https://", "http://")) else "",
        "ad_headline": value("headline", 255),
        "ctwa_clid": value("ctwa_clid", 255),
    }


@dataclass(frozen=True)
class CodeMessageResult:
    offer: OfferCode
    claim: OfferClaim | None
    created: bool
    reply: Message | None


def handle_code_message(message_id) -> CodeMessageResult | None:
    """Answer an inbound offer-code message: record the claim (once per wamid, within the
    per-contact and total limits), reply, and apply the offer to an open checkout.

    Idempotent: a webhook retry finds the claim by wamid and the reply by its idempotency key.
    """
    message = (
        Message.objects.select_related("conversation__contact", "workspace")
        .filter(pk=message_id, direction=Message.Direction.INBOUND, type=Message.Type.TEXT)
        .first()
    )
    if message is None or not commerce_enabled(message.workspace_id):
        return None
    offer = match_code(message.workspace_id, message.text)
    if offer is None:
        return None
    conversation = message.conversation
    contact = conversation.contact
    wamid = message.wamid or ""

    created = False
    with transaction.atomic():
        offer = OfferCode.objects.select_for_update().get(pk=offer.pk)
        claim = OfferClaim.objects.filter(offer=offer, wamid=wamid).first() if wamid else None
        if claim is None:
            previous = (
                OfferClaim.objects.filter(offer=offer, contact=contact)
                .order_by("-created_at")
                .first()
            )
            contact_claims = OfferClaim.objects.filter(offer=offer, contact=contact).count()
            if contact_claims < offer.max_uses_per_contact and has_capacity(offer):
                try:
                    with transaction.atomic():
                        claim = OfferClaim.objects.create(
                            workspace_id=message.workspace_id,
                            offer=offer,
                            contact=contact,
                            conversation=conversation,
                            message=message,
                            wamid=wamid,
                            **_referral(message.payload),
                        )
                    created = True
                except IntegrityError:
                    claim = OfferClaim.objects.filter(offer=offer, wamid=wamid).first()
            else:
                claim = previous  # a repeat send: just re-send the reply
        reply = _send_reply(offer, conversation, wamid or str(message.pk), claim is not None)

    if claim is not None and claim.status == CLAIMED:
        from apps.orders import services as order_services

        try:
            order_services.apply_offer_to_active_checkout(conversation.pk)
        except Exception:
            logger.exception("Applying offer %s to the active checkout failed", offer.pk)
    return CodeMessageResult(offer=offer, claim=claim, created=created, reply=reply)


def _send_reply(offer: OfferCode, conversation, key: str, has_claim: bool) -> Message | None:
    if has_claim:
        content = _offer_content(offer, conversation)
    else:
        content = sending.TextContent(FULLY_CLAIMED_TEXT)
    try:
        return sending.send_message(
            workspace=conversation.workspace,
            contact=conversation.contact,
            conversation=conversation,
            content=content,
            source=Message.Source.COMMERCE,
            source_ref=f"{SOURCE_REF_PREFIX}{offer.pk}",
            idempotency_key=f"offers:reply:{key}"[:255],
        )
    except (sending.SendPolicyError, InvalidInteractiveContent, ValidationError) as exc:
        logger.info("Offer reply to contact %s not sent: %s", conversation.contact_id, exc)
        return None


def _offer_content(offer: OfferCode, conversation):
    label = _shop_button_label(conversation)
    if label is None:
        return sending.TextContent(offer.reply_text)
    return reply_buttons(
        offer.reply_text,
        [(build_reply_id("shop", "browse"), label), (build_reply_id("shop", "menu"), MENU)],
    )


def _shop_button_label(conversation) -> str | None:
    """ "Shop now" / "Book now" when the store is on, the chat is on the store number and there is
    something to buy; None otherwise."""
    from apps.catalog import services as catalog_services
    from apps.orders import services as order_services

    store = StoreSettings.objects.filter(
        workspace_id=conversation.workspace_id, enabled=True
    ).first()
    if store is None:
        return None
    number = order_services.store_phone_number(store)
    if number is None or number.pk != conversation.phone_number_id:
        return None
    items = catalog_services.shoppable_products(conversation.workspace)
    if not items.exists():
        return None
    model = items.model
    has_kind = any(field.name == "kind" for field in model._meta.get_fields())
    if has_kind and not items.exclude(kind="service").exists():
        return BOOK_NOW
    return SHOP_NOW


# --- Redemption ---------------------------------------------------------------------------------


def redeem_claim(claim: OfferClaim, *, bill_paise: int | None = None, user=None) -> OfferClaim:
    """``claimed``/``applied`` → ``redeemed`` (staff at the counter)."""
    now = timezone.now()
    with transaction.atomic():
        claim = (
            OfferClaim.objects.select_for_update(of=("self",))
            .select_related("order")
            .get(pk=claim.pk)
        )
        if claim.status not in (CLAIMED, APPLIED):
            raise InvalidClaimTransition()
        if bill_paise is None and claim.order is not None:
            bill_paise = claim.order.total_paise
        claim.status = REDEEMED
        claim.bill_paise = bill_paise
        claim.redeemed_at = now
        claim.redeemed_by = user if getattr(user, "is_authenticated", False) else None
        claim.save(
            update_fields=["status", "bill_paise", "redeemed_at", "redeemed_by", "updated_at"]
        )
    return claim


def redeem_at_counter(
    workspace, *, code: str, phone: str, bill_paise: int | None = None, user=None
) -> OfferClaim:
    """Redeem ``code`` for the buyer with ``phone``: their open claim, else a new counter claim
    (the contact is created when new). Raises ``OfferUnavailable`` when the offer can't be used."""
    offer = OfferCode.objects.filter(
        workspace=workspace, code=str(code or "").strip().upper()
    ).first()
    if offer is None:
        raise ValidationError({"code": ["No offer has this code."]})
    try:
        phone_e164 = normalize_e164(phone)
    except InvalidPhoneNumber as exc:
        raise ValidationError({"phone": [str(exc)]}) from None
    if not is_live(offer):
        raise OfferUnavailable()

    with transaction.atomic():
        offer = OfferCode.objects.select_for_update().get(pk=offer.pk)
        contact = Contact.objects.filter(workspace=workspace, phone_e164=phone_e164).first()
        if contact is None:
            entitlements.check_quota(workspace, entitlements.CONTACTS)
            contact = contact_services.get_or_create_from_wa(workspace, phone_e164)
        claim = (
            OfferClaim.objects.filter(offer=offer, contact=contact, status__in=(CLAIMED, APPLIED))
            .order_by("-created_at")
            .first()
        )
        if claim is None:
            contact_claims = OfferClaim.objects.filter(offer=offer, contact=contact).count()
            if contact_claims >= offer.max_uses_per_contact or not has_capacity(offer):
                raise OfferUnavailable()
            claim = OfferClaim.objects.create(workspace=workspace, offer=offer, contact=contact)
        elif claim.status == CLAIMED and not has_capacity(offer):
            raise OfferUnavailable()
        return redeem_claim(claim, bill_paise=bill_paise, user=user)


# --- Stats --------------------------------------------------------------------------------------


def _zone(workspace) -> ZoneInfo:
    try:
        return ZoneInfo(workspace.time_zone)
    except (KeyError, ValueError):
        return ZoneInfo("Asia/Kolkata")


def offer_stats(offer: OfferCode, *, days: int = STATS_DAYS) -> dict:
    claims = OfferClaim.objects.filter(offer=offer)
    totals = claims.aggregate(
        claims=Count("id"),
        from_ads=Count("id", filter=~Q(ad_source_id="") | ~Q(ctwa_clid="")),
        applied=Count("id", filter=Q(status=APPLIED)),
        redeemed=Count("id", filter=Q(status=REDEEMED)),
        discount_paise=Sum("discount_paise", filter=Q(status=REDEEMED)),
        revenue_paise=Sum("bill_paise", filter=Q(status=REDEEMED)),
    )
    zone = _zone(offer.workspace)
    today = timezone.localdate(timezone.now(), zone)
    first_day = today - timedelta(days=days - 1)
    claimed_by_day = dict(
        claims.filter(created_at__date__gte=first_day - timedelta(days=1))
        .annotate(day=TruncDate("created_at", tzinfo=zone))
        .values("day")
        .annotate(n=Count("id"))
        .values_list("day", "n")
    )
    redeemed_by_day = dict(
        claims.filter(status=REDEEMED, redeemed_at__date__gte=first_day - timedelta(days=1))
        .annotate(day=TruncDate("redeemed_at", tzinfo=zone))
        .values("day")
        .annotate(n=Count("id"))
        .values_list("day", "n")
    )
    daily = []
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        daily.append(
            {
                "date": day,
                "claims": claimed_by_day.get(day, 0),
                "redeemed": redeemed_by_day.get(day, 0),
            }
        )
    return {
        "claims": totals["claims"] or 0,
        "from_ads": totals["from_ads"] or 0,
        "applied": totals["applied"] or 0,
        "redeemed": totals["redeemed"] or 0,
        "discount_paise": totals["discount_paise"] or 0,
        "revenue_paise": totals["revenue_paise"] or 0,
        "daily": daily,
    }
