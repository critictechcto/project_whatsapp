"""Payments services (docs/contracts/wave-3-commerce.md, "Payments services").

Confirmation needs no seller webhook: the buyer's return page, ``payments.poll_open_links`` and
the optional webhook all end in :func:`apply_link_state`, which locks the link row, checks the
amount and currency, and emits ``PaymentLinkPaid`` / ``PaymentLinkExpired`` /
``PaymentLinkCancelled`` exactly once on commit. Gateway calls never run while a row lock is
held.

Secrets are never logged; ``last_error`` values are scrubbed of the account's secrets.
"""

import json
import logging
import re
from datetime import datetime, timedelta
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers

from common.events import (
    PaymentLinkCancelled,
    PaymentLinkExpired,
    PaymentLinkPaid,
    emit,
    payment_link_cancelled,
    payment_link_expired,
    payment_link_paid,
)

from .exceptions import PaymentAccountInvalid, PaymentAccountMissing, PaymentProviderError
from .models import CURRENCY, PaymentAccount, PaymentLink, PaymentWebhookEvent
from .providers import (
    CANCELLED,
    CREATED,
    EXPIRED,
    PAID,
    PARTIALLY_PAID,
    LinkRequest,
    LinkState,
    get_provider,
)

logger = logging.getLogger(__name__)

__all__ = [
    "PaymentAccountInvalid",
    "PaymentAccountMissing",
    "PaymentProviderError",
    "apply_link_state",
    "cancel_payment_link",
    "create_payment_link",
    "get_account",
    "handle_merchant_webhook",
    "online_payments_ready",
    "poll_due_links",
    "refresh_payment_link",
    "return_url",
    "update_account",
    "verify_account",
    "webhook_url",
]

RAZORPAY_KEY_ID_RE = re.compile(r"^rzp_(test|live)_[A-Za-z0-9]+$")
CASHFREE_KEY_ID_RE = re.compile(r"^\S+$")

# Polls run this many minutes after creation, then once at expires_at + FINAL_POLL_DELAY.
POLL_OFFSETS_MINUTES = (2, 4, 6, 10, 15, 20, 25, 30)
FINAL_POLL_DELAY = timedelta(minutes=2)
FINAL_POLL_RETRY = timedelta(minutes=5)
# A final poll that keeps failing expires the link locally after this many retries.
MAX_FINAL_POLL_RETRIES = 6
POLL_BATCH_SIZE = 100

TERMINAL_STATUSES = frozenset(
    {
        PaymentLink.Status.PAID,
        PaymentLink.Status.EXPIRED,
        PaymentLink.Status.CANCELLED,
        PaymentLink.Status.FAILED,
    }
)


# --- Accounts --------------------------------------------------------------------------------


def get_account(workspace) -> PaymentAccount | None:
    return PaymentAccount.objects.filter(workspace=workspace).first()


def online_payments_ready(workspace) -> bool:
    """True when the workspace has a verified gateway account with its keys and mode.

    No webhook is needed: payments are confirmed by the buyer's return and by polling.
    """
    account = get_account(workspace)
    return bool(
        account is not None
        and account.status == PaymentAccount.Status.VERIFIED
        and account.key_id
        and account.key_secret
        and account.mode
    )


def _scrub(message: str, account: PaymentAccount) -> str:
    for secret in (account.key_secret, account.webhook_secret):
        if secret:
            message = message.replace(secret, "***")
    return message[:500]


def update_account(workspace, data: dict) -> PaymentAccount:
    """Apply a validated ``PaymentAccountRequest`` (contract rules; 400 on field errors)."""
    with transaction.atomic():
        account = PaymentAccount.objects.select_for_update().filter(
            workspace=workspace
        ).first() or PaymentAccount(workspace=workspace)
        before = (account.provider, account.key_id, account.key_secret, account.mode)
        errors: dict[str, list[str]] = {}

        provider = data.get("provider", account.provider)
        if provider != account.provider:
            account.provider = provider
            account.key_id = account.key_secret = account.webhook_secret = account.mode = ""
        if "key_id" in data:
            account.key_id = data["key_id"].strip()
        if "key_secret" in data:
            account.key_secret = data["key_secret"].strip()
        requested_mode = (data["mode"] or "") if "mode" in data else None

        if provider == PaymentAccount.Provider.RAZORPAY:
            if "webhook_secret" in data:
                account.webhook_secret = data["webhook_secret"].strip()
            if account.key_id:
                match = RAZORPAY_KEY_ID_RE.fullmatch(account.key_id)
                if match is None:
                    errors["key_id"] = [
                        "Use a Razorpay key id that starts with rzp_test_ or rzp_live_."
                    ]
                else:
                    if requested_mode and requested_mode != match.group(1):
                        errors["mode"] = [f"This key id is for {match.group(1)} mode."]
                    account.mode = match.group(1)
            elif requested_mode is not None:
                account.mode = requested_mode
        else:
            if "webhook_secret" in data:
                errors["webhook_secret"] = [
                    "Cashfree signs webhooks with your secret key; no webhook secret is needed."
                ]
            if requested_mode is not None:
                account.mode = requested_mode
            if account.key_id and not CASHFREE_KEY_ID_RE.fullmatch(account.key_id):
                errors["key_id"] = ["Paste the App ID without spaces."]
            if (account.key_id or account.key_secret) and not account.mode:
                errors["mode"] = ["Choose test (sandbox) or live mode for Cashfree."]

        if errors:
            raise serializers.ValidationError(errors)

        if (account.provider, account.key_id, account.key_secret, account.mode) != before:
            has_keys = bool(account.key_id and account.key_secret)
            account.status = (
                PaymentAccount.Status.UNVERIFIED
                if has_keys
                else PaymentAccount.Status.NOT_CONFIGURED
            )
            account.verified_at = None
            account.last_error = ""
        account.save()
    return account


def verify_account(account: PaymentAccount) -> PaymentAccount:
    """One authenticated read on the gateway; marks the account verified or invalid.

    Raises ``PaymentAccountMissing``, ``PaymentAccountInvalid`` (after saving ``invalid``) or
    ``PaymentProviderError`` (after saving ``last_error``; the status is unchanged).
    """
    if not account.key_id or not account.key_secret or not account.mode:
        raise PaymentAccountMissing()
    try:
        get_provider(account).verify_credentials()
    except PaymentAccountInvalid:
        account.status = PaymentAccount.Status.INVALID
        account.verified_at = None
        account.last_error = "The gateway rejected these API keys."
        account.save(update_fields=["status", "verified_at", "last_error", "updated_at"])
        raise
    except PaymentProviderError as exc:
        account.last_error = _scrub(f"Could not reach the gateway: {exc}", account)
        account.save(update_fields=["last_error", "updated_at"])
        raise
    account.status = PaymentAccount.Status.VERIFIED
    account.verified_at = timezone.now()
    account.last_error = ""
    account.save(update_fields=["status", "verified_at", "last_error", "updated_at"])
    return account


def _mark_account_invalid(account: PaymentAccount) -> None:
    PaymentAccount.objects.filter(pk=account.pk).update(
        status=PaymentAccount.Status.INVALID,
        verified_at=None,
        last_error="The gateway rejected these API keys.",
        updated_at=timezone.now(),
    )


# --- URLs ------------------------------------------------------------------------------------


def _absolute(path: str) -> str:
    return f"{settings.PUBLIC_API_BASE_URL.rstrip('/')}{path}"


def webhook_url(account: PaymentAccount) -> str:
    """Optional webhook URL for the gateway settings; "" for an account that isn't saved yet."""
    if account.pk is None or account._state.adding or not account.webhook_token:
        return ""
    return _absolute(reverse("payments_webhooks:merchant-webhook", args=[account.webhook_token]))


def return_url(payment_link: PaymentLink) -> str:
    """Where the gateway sends the buyer after paying."""
    return _absolute(reverse("payments_return:link-return", args=[payment_link.pk]))


# --- Poll schedule ---------------------------------------------------------------------------


def next_poll_at(link: PaymentLink, poll_count: int) -> datetime | None:
    """When poll number ``poll_count`` (0-based) is due; None after the final poll."""
    if poll_count < len(POLL_OFFSETS_MINUTES):
        return link.created_at + timedelta(minutes=POLL_OFFSETS_MINUTES[poll_count])
    if poll_count == len(POLL_OFFSETS_MINUTES):
        last_scheduled = link.created_at + timedelta(minutes=POLL_OFFSETS_MINUTES[-1])
        if link.expires_at is None:
            return last_scheduled + FINAL_POLL_DELAY
        return max(link.expires_at + FINAL_POLL_DELAY, last_scheduled)
    return None


def is_final_poll(link: PaymentLink, poll_count: int, now: datetime) -> bool:
    if poll_count >= len(POLL_OFFSETS_MINUTES):
        return True
    return link.expires_at is not None and now >= link.expires_at + FINAL_POLL_DELAY


# --- Links -----------------------------------------------------------------------------------


def _usable_account(workspace) -> PaymentAccount:
    account = get_account(workspace)
    if account is None or not account.key_id or not account.key_secret or not account.mode:
        raise PaymentAccountMissing()
    if account.status == PaymentAccount.Status.INVALID:
        raise PaymentAccountInvalid()
    return account


def create_payment_link(
    *,
    workspace,
    order_id: UUID,
    reference_id: str,
    amount_paise: int,
    description: str,
    customer_name: str,
    customer_phone_e164: str,
    expire_by: datetime,
) -> PaymentLink:
    """Create a payment link on the seller's gateway account; idempotent on ``reference_id``.

    The outbox row is saved ``creating`` before the gateway call. Raises
    :class:`PaymentAccountMissing` / :class:`PaymentAccountInvalid` (409) or
    :class:`PaymentProviderError` (check ``retryable``; a non-retryable error marks the link
    ``failed``).
    """
    account = _usable_account(workspace)
    link = PaymentLink.objects.filter(workspace=workspace, reference_id=reference_id).first()
    if link is None:
        try:
            with transaction.atomic():
                link = PaymentLink.objects.create(
                    workspace=workspace,
                    order_id=order_id,
                    provider=account.provider,
                    reference_id=reference_id,
                    amount_paise=amount_paise,
                    currency=CURRENCY,
                    status=PaymentLink.Status.CREATING,
                    expires_at=expire_by,
                )
        except IntegrityError:
            link = PaymentLink.objects.get(workspace=workspace, reference_id=reference_id)
    if link.status != PaymentLink.Status.CREATING:
        return link

    provider = get_provider(account)
    request = LinkRequest(
        reference_id=reference_id,
        amount_paise=link.amount_paise,
        currency=link.currency,
        description=description,
        customer_name=customer_name,
        customer_phone_e164=customer_phone_e164,
        expire_by=link.expires_at or expire_by,
        return_url=return_url(link),
        notes={"workspace_id": str(workspace.pk), "order_id": str(link.order_id)},
    )
    try:
        state = provider.create_link(request)
    except PaymentAccountInvalid:
        _mark_account_invalid(account)
        _record_create_error(link, "The gateway rejected the API keys.", failed=True)
        raise
    except PaymentProviderError as exc:
        if exc.status_code in (401, 403):
            _mark_account_invalid(account)
            _record_create_error(link, "The gateway rejected the API keys.", failed=True)
            raise PaymentAccountInvalid() from None
        _record_create_error(link, _scrub(str(exc), account), failed=not exc.retryable)
        raise
    return _apply_created(link, state, provider)


def _record_create_error(link: PaymentLink, message: str, *, failed: bool) -> None:
    changes = {"last_error": message[:500], "updated_at": timezone.now()}
    if failed:
        changes["status"] = PaymentLink.Status.FAILED
    PaymentLink.objects.filter(pk=link.pk, status=PaymentLink.Status.CREATING).update(**changes)
    logger.warning("Payment link %s creation failed (final=%s): %s", link.pk, failed, message)


def _apply_created(link: PaymentLink, state: LinkState, provider) -> PaymentLink:
    cancel_on_gateway = False
    with transaction.atomic():
        locked = PaymentLink.objects.select_for_update().get(pk=link.pk)
        if locked.status == PaymentLink.Status.CREATING:
            locked.provider_link_id = state.provider_link_id[:100]
            locked.short_url = state.short_url[:255]
            locked.status = PaymentLink.Status.CREATED
            locked.expires_at = state.expires_at or locked.expires_at
            locked.last_error = ""
            locked.raw = dict(state.raw)
            locked.poll_count = 0
            locked.next_poll_at = next_poll_at(locked, 0)
            locked.save()
        elif locked.status == PaymentLink.Status.CANCELLED and not locked.provider_link_id:
            # Cancelled while the gateway call was in flight: cancel the new link too.
            locked.provider_link_id = state.provider_link_id[:100]
            locked.short_url = state.short_url[:255]
            locked.save(update_fields=["provider_link_id", "short_url", "updated_at"])
            cancel_on_gateway = True
    if cancel_on_gateway:
        try:
            provider.cancel_link(state.provider_link_id)
        except PaymentProviderError as exc:
            logger.warning("Could not cancel payment link %s on the gateway: %s", link.pk, exc)
        return locked
    if locked.status == PaymentLink.Status.CREATED and state.status != CREATED:
        return apply_link_state(locked, state)  # e.g. an idempotent retry of a paid link
    return locked


def cancel_payment_link(payment_link: PaymentLink) -> PaymentLink:
    """Cancel an open link; idempotent, and never cancels a paid link."""
    current = PaymentLink.objects.get(pk=payment_link.pk)
    if current.status in TERMINAL_STATUSES:
        return current
    if not current.provider_link_id:
        return _close_locally(current, PaymentLink.Status.CANCELLED)
    account = PaymentAccount.objects.filter(workspace_id=current.workspace_id).first()
    if account is None or account.provider != current.provider:
        logger.warning("Payment link %s cancelled locally: the gateway account is gone", current.pk)
        return _close_locally(current, PaymentLink.Status.CANCELLED)
    state = get_provider(account).cancel_link(current.provider_link_id)
    return apply_link_state(current, state)


def refresh_payment_link(payment_link: PaymentLink) -> PaymentLink:
    """Fetch the link from the gateway and apply its state (emitting payment events once)."""
    return _refresh(payment_link, final=False)


def _refresh(payment_link: PaymentLink, *, final: bool) -> PaymentLink:
    current = PaymentLink.objects.get(pk=payment_link.pk)
    if current.status in TERMINAL_STATUSES or not current.provider_link_id:
        return current
    account = PaymentAccount.objects.filter(workspace_id=current.workspace_id).first()
    if account is None or account.provider != current.provider or not account.key_secret:
        logger.warning("Payment link %s can't be refreshed: no gateway account", current.pk)
        if final:
            return _close_locally(current, PaymentLink.Status.EXPIRED)
        return current
    provider = get_provider(account)
    state = provider.fetch_link(current.provider_link_id)
    if final and state.status in (CREATED, PARTIALLY_PAID):
        # Past expiry: stop late payments on the gateway, then expire the link here.
        try:
            state = provider.cancel_link(current.provider_link_id)
        except PaymentProviderError as exc:
            logger.warning("Could not cancel expired payment link %s: %s", current.pk, exc)
        if state.status == PAID:
            return apply_link_state(current, state)
        if state.status == PARTIALLY_PAID:
            logger.warning(
                "Payment link %s expired partially paid (%s paise); refund it in the gateway",
                current.pk,
                state.amount_paid_paise,
            )
        return _close_locally(current, PaymentLink.Status.EXPIRED)
    return apply_link_state(current, state)


def _payment_problem(link: PaymentLink, state: LinkState) -> str:
    currency = (state.currency or link.currency).upper()
    if currency != link.currency:
        return f"Paid in {currency}, expected {link.currency}; the order is not confirmed."
    if state.amount_paise is not None and state.amount_paise != link.amount_paise:
        return (
            f"The gateway link is for {state.amount_paise} paise, expected "
            f"{link.amount_paise}; the order is not confirmed."
        )
    if state.amount_paid_paise != link.amount_paise:
        return (
            f"Paid {state.amount_paid_paise} paise, expected {link.amount_paise}; "
            "the order is not confirmed."
        )
    return ""


def apply_link_state(payment_link: PaymentLink, state: LinkState) -> PaymentLink:
    """Apply a gateway ``LinkState`` under a row lock; emits events once, on commit."""
    with transaction.atomic():
        link = PaymentLink.objects.select_for_update().get(pk=payment_link.pk)
        if link.status in TERMINAL_STATUSES:
            return link
        if link.provider_link_id and state.provider_link_id not in ("", link.provider_link_id):
            logger.warning("Ignoring gateway state for another link on %s", link.pk)
            return link
        now = timezone.now()
        link.raw = dict(state.raw)
        if state.short_url and not link.short_url:
            link.short_url = state.short_url[:255]

        if state.status == PAID:
            problem = _payment_problem(link, state)
            if problem:
                logger.warning("Payment link %s paid with a mismatch: %s", link.pk, problem)
                link.last_error = problem
            else:
                link.status = PaymentLink.Status.PAID
                link.paid_at = state.paid_at or now
                link.provider_payment_id = state.provider_payment_id[:100]
                link.next_poll_at = None
                link.last_error = ""
        elif state.status == PARTIALLY_PAID:
            logger.warning(
                "Payment link %s partially paid (%s of %s paise); not confirming",
                link.pk,
                state.amount_paid_paise,
                link.amount_paise,
            )
            link.last_error = (
                f"Partial payment of {state.amount_paid_paise} paise received; "
                "the order is not confirmed."
            )
        elif state.status == EXPIRED:
            link.status = PaymentLink.Status.EXPIRED
            link.next_poll_at = None
        elif state.status == CANCELLED:
            link.status = PaymentLink.Status.CANCELLED
            link.cancelled_at = now
            link.next_poll_at = None
        link.save()
        if link.status in TERMINAL_STATUSES:
            _emit_on_commit(link, now)
    return link


def _close_locally(payment_link: PaymentLink, status: str) -> PaymentLink:
    with transaction.atomic():
        link = PaymentLink.objects.select_for_update().get(pk=payment_link.pk)
        if link.status in TERMINAL_STATUSES:
            return link
        now = timezone.now()
        link.status = status
        link.next_poll_at = None
        if status == PaymentLink.Status.CANCELLED:
            link.cancelled_at = now
        link.save()
        _emit_on_commit(link, now)
    return link


def _emit_on_commit(link: PaymentLink, occurred_at: datetime) -> None:
    common = {
        "workspace_id": link.workspace_id,
        "order_id": link.order_id,
        "payment_link_id": link.pk,
        "provider": link.provider,
        "provider_link_id": link.provider_link_id,
    }
    if link.status == PaymentLink.Status.PAID:
        signal, event = (
            payment_link_paid,
            PaymentLinkPaid(
                **common,
                provider_payment_id=link.provider_payment_id,
                amount_paise=link.amount_paise,
                currency=link.currency,
                paid_at=link.paid_at,
            ),
        )
    elif link.status == PaymentLink.Status.EXPIRED:
        signal, event = payment_link_expired, PaymentLinkExpired(**common, occurred_at=occurred_at)
    elif link.status == PaymentLink.Status.CANCELLED:
        signal, event = (
            payment_link_cancelled,
            PaymentLinkCancelled(**common, occurred_at=occurred_at),
        )
    else:
        return
    transaction.on_commit(lambda: emit(signal, event))


def poll_due_links(*, now: datetime | None = None, batch_size: int = POLL_BATCH_SIZE) -> int:
    """Refresh ``created`` links whose ``next_poll_at`` has passed; returns how many."""
    now = now or timezone.now()
    claimed: list[tuple[PaymentLink, bool]] = []
    with transaction.atomic():
        due = (
            PaymentLink.objects.select_for_update(skip_locked=True)
            .filter(status=PaymentLink.Status.CREATED, next_poll_at__lte=now)
            .order_by("next_poll_at")[:batch_size]
        )
        for link in due:
            final = is_final_poll(link, link.poll_count, now)
            link.poll_count += 1
            link.next_poll_at = (
                now + FINAL_POLL_RETRY if final else next_poll_at(link, link.poll_count)
            )
            link.save(update_fields=["poll_count", "next_poll_at", "updated_at"])
            claimed.append((link, final))

    for link, final in claimed:
        try:
            _refresh(link, final=final)
        except (PaymentProviderError, PaymentAccountMissing, PaymentAccountInvalid) as exc:
            logger.warning("Polling payment link %s failed: %s", link.pk, exc)
            too_many = link.poll_count > len(POLL_OFFSETS_MINUTES) + MAX_FINAL_POLL_RETRIES
            if final and too_many:
                _close_locally(link, PaymentLink.Status.EXPIRED)
        except Exception:
            logger.exception("Polling payment link %s crashed", link.pk)
    return len(claimed)


# --- Optional merchant webhook ---------------------------------------------------------------


def handle_merchant_webhook(account: PaymentAccount, headers, body: bytes) -> int:
    """Verify, dedupe and apply one gateway webhook delivery; returns the events applied.

    Raises ``InvalidWebhookSignature`` (the view answers 400). Anything after a valid signature
    is best effort: polling still confirms links whose update fails here.
    """
    updates = get_provider(account).parse_webhook(headers, body)
    try:
        payload = json.loads(body)
    except ValueError:
        payload = {}
    payload = payload if isinstance(payload, dict) else {}
    applied = 0
    for update in updates:
        try:
            with transaction.atomic():
                event, created = PaymentWebhookEvent.objects.get_or_create(
                    workspace_id=account.workspace_id,
                    event_id=update.event_id,
                    defaults={"event_type": update.event_type[:64], "payload": payload},
                )
        except IntegrityError:
            continue
        if not created and event.processed_at is not None:
            continue
        link = PaymentLink.objects.filter(
            workspace_id=account.workspace_id,
            provider=account.provider,
            provider_link_id=update.provider_link_id,
        ).first()
        if link is None:
            logger.info("Webhook %s is for a link we don't know", update.event_type)
        else:
            try:
                if update.state is not None:
                    apply_link_state(link, update.state)
                else:
                    refresh_payment_link(link)
            except (PaymentProviderError, PaymentAccountMissing, PaymentAccountInvalid) as exc:
                logger.warning("Webhook for payment link %s not applied: %s", link.pk, exc)
                continue
        PaymentWebhookEvent.objects.filter(pk=event.pk).update(processed_at=timezone.now())
        applied += 1
    return applied
