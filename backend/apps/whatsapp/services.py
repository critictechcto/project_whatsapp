"""WhatsApp Business Account onboarding (Embedded Signup), sync and disconnect."""

import re
import secrets
from datetime import UTC, datetime
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import exceptions

from common.exceptions import Conflict, UpstreamUnavailable
from common.phone import InvalidPhoneNumber, normalize_e164

from .client import GraphAPIError, GraphClient, get_client
from .client.errors import GraphPermissionError, InvalidParameterError, TokenInvalidError
from .models import PhoneNumber, WhatsAppBusinessAccount

MANAGEMENT_SCOPE = "whatsapp_business_management"
RECONNECT_REQUIRED = "Reconnect required"
_NON_DIGITS = re.compile(r"\D")


class SignupRejected(exceptions.APIException):
    status_code = 400
    default_code = "signup_rejected"
    default_detail = "Embedded Signup could not be completed."


class MetaRequestFailed(exceptions.APIException):
    status_code = 400
    default_code = "meta_request_failed"
    default_detail = "Meta rejected the request."


def digits_only(value: str) -> str:
    return _NON_DIGITS.sub("", value or "")


def _clip(value: Any, length: int) -> str:
    return str(value or "")[:length]


def _api_error(exc: GraphAPIError) -> exceptions.APIException:
    """Translate a Graph error into an API error without leaking anything but Meta's message."""
    if exc.retryable:
        return UpstreamUnavailable()
    return MetaRequestFailed(exc.message or MetaRequestFailed.default_detail)


# --- Embedded Signup ---------------------------------------------------------------------------


def _verify_grant(debug: dict, waba_id: str) -> None:
    """The token must be valid, issued to our app and granted management of ``waba_id``."""
    granted = any(
        isinstance(scope, dict)
        and scope.get("scope") == MANAGEMENT_SCOPE
        and waba_id in {str(target) for target in scope.get("target_ids") or []}
        for scope in debug.get("granular_scopes") or []
    )
    if not (
        debug.get("is_valid") is True
        and str(debug.get("app_id", "")) == str(settings.META_APP_ID)
        and granted
    ):
        raise SignupRejected(
            "The signup did not grant this app access to that WhatsApp Business Account.",
            code="waba_not_granted",
        )


def _token_expiry(debug: dict) -> datetime | None:
    expires_at = debug.get("expires_at")
    if not isinstance(expires_at, int | float) or expires_at <= 0:
        return None
    return datetime.fromtimestamp(expires_at, tz=UTC)


def apply_phone_data(phone: PhoneNumber, data: dict) -> None:
    """Copy Meta's phone number fields onto ``phone``. Absent keys keep their current value."""
    if data.get("display_phone_number"):
        phone.display_phone_number = _clip(data["display_phone_number"], 32)
        try:
            phone.phone_e164 = normalize_e164(phone.display_phone_number)
        except InvalidPhoneNumber:
            phone.phone_e164 = ""
    if "verified_name" in data:
        phone.verified_name = _clip(data["verified_name"], 255)
    if "name_status" in data:
        phone.name_status = _clip(data["name_status"], 32)
    if "quality_rating" in data:
        rating = str(data["quality_rating"] or "").upper()
        phone.quality_rating = (
            rating
            if rating in PhoneNumber.QualityRating.values
            else PhoneNumber.QualityRating.UNKNOWN
        )
    if "messaging_limit_tier" in data:
        phone.messaging_limit_tier = _clip(data["messaging_limit_tier"], 32)
    if isinstance(data.get("throughput"), dict):
        phone.throughput_level = _clip(data["throughput"].get("level"), 32)
    if "platform_type" in data:
        phone.platform_type = _clip(data["platform_type"], 32)
    if "code_verification_status" in data:
        phone.code_verification_status = _clip(data["code_verification_status"], 32)
    if "status" in data:
        phone.meta_status = _clip(data["status"], 32)


def complete_embedded_signup(
    *,
    workspace,
    user,
    code: str,
    waba_id: str,
    phone_number_id: str | None = None,
    business_id: str = "",
    coexistence: bool = False,
) -> WhatsAppBusinessAccount:
    """Exchange the Embedded Signup code, verify the grant and store the WABA and its numbers.

    Webhook subscription and phone registration continue in ``whatsapp.finish_onboarding``.
    """
    app_client = get_client()
    try:
        token = app_client.exchange_code(code).get("access_token")
    except GraphAPIError as exc:
        if exc.retryable:
            raise UpstreamUnavailable() from None
        raise SignupRejected(
            "The signup code is invalid or has expired. Please try again.",
            code="signup_code_invalid",
        ) from None
    if not token:
        raise SignupRejected("Meta did not return an access token.", code="signup_code_invalid")

    try:
        debug = app_client.debug_token(token)
    except GraphAPIError as exc:
        raise _api_error(exc) from None
    _verify_grant(debug, waba_id)

    customer_client = get_client(token)
    try:
        waba_data = customer_client.get_waba(waba_id)
        numbers = customer_client.list_phone_numbers(waba_id)
    except GraphAPIError as exc:
        raise _api_error(exc) from None

    number_ids = {str(number.get("id")) for number in numbers}
    if phone_number_id and phone_number_id not in number_ids:
        raise SignupRejected(
            "That phone number does not belong to the WhatsApp Business Account.",
            code="phone_number_not_in_waba",
        )

    with transaction.atomic():
        waba = WhatsAppBusinessAccount.objects.select_for_update().filter(waba_id=waba_id).first()
        if waba is not None and waba.workspace_id != workspace.pk:
            raise Conflict(
                "This WhatsApp Business Account is connected to another workspace.",
                code="waba_already_connected",
            )
        foreign_numbers = PhoneNumber.objects.filter(phone_number_id__in=number_ids).exclude(
            workspace=workspace
        )
        if foreign_numbers.exists():
            raise Conflict(
                "A phone number on this account is connected to another workspace.",
                code="phone_number_already_connected",
            )

        waba = waba or WhatsAppBusinessAccount(workspace=workspace, waba_id=waba_id)
        waba.business_id = business_id or waba.business_id
        waba.name = _clip(waba_data.get("name"), 255)
        waba.currency = _clip(waba_data.get("currency"), 8)
        waba.timezone_id = _clip(waba_data.get("timezone_id"), 16)
        waba.message_template_namespace = _clip(waba_data.get("message_template_namespace"), 128)
        waba.access_token = token
        waba.token_expires_at = _token_expiry(debug)
        waba.status = WhatsAppBusinessAccount.Status.PENDING
        waba.onboarding_status = WhatsAppBusinessAccount.OnboardingStatus.CODE_EXCHANGED
        waba.subscribed_at = None
        waba.last_error = ""
        waba.connected_by = user
        waba.save()

        existing = {
            phone.phone_number_id: phone
            for phone in PhoneNumber.objects.select_for_update().filter(
                phone_number_id__in=number_ids
            )
        }
        phones: list[PhoneNumber] = []
        for number in numbers:
            number_id = str(number.get("id"))
            phone = existing.get(number_id) or PhoneNumber(
                workspace=workspace, waba=waba, phone_number_id=number_id
            )
            phone.waba = waba
            apply_phone_data(phone, number)
            if coexistence and number_id == phone_number_id:
                phone.is_coexistence = True
            phone.last_synced_at = timezone.now()
            phone.save()
            phones.append(phone)

        if phones and not PhoneNumber.objects.filter(workspace=workspace, is_default=True).exists():
            default = next((p for p in phones if p.phone_number_id == phone_number_id), phones[0])
            default.is_default = True
            default.save(update_fields=["is_default", "updated_at"])

        enqueue_finish_onboarding(waba)

    waba.refresh_from_db()
    return waba


def enqueue_finish_onboarding(waba: WhatsAppBusinessAccount) -> None:
    from .tasks import finish_onboarding

    waba_pk = str(waba.pk)
    transaction.on_commit(lambda: finish_onboarding.delay(waba_pk))


# --- Onboarding steps (used by tasks) ----------------------------------------------------------


def generate_pin() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def register_phone_number(phone: PhoneNumber, client: GraphClient) -> None:
    """Register ``phone`` for Cloud API. The PIN is stored (encrypted) before calling Meta, so a
    crash after Meta accepted it can retry with the same PIN."""
    if (
        phone.is_coexistence
        or phone.registration_status == PhoneNumber.RegistrationStatus.REGISTERED
    ):
        return
    if not phone.pin:
        phone.pin = generate_pin()
        phone.save(update_fields=["pin", "updated_at"])
    try:
        client.register_phone(phone.phone_number_id, phone.pin)
    except GraphAPIError as exc:
        if not exc.retryable:
            phone.registration_status = PhoneNumber.RegistrationStatus.FAILED
            phone.last_error = exc.message
            phone.save(update_fields=["registration_status", "last_error", "updated_at"])
        raise
    phone.registration_status = PhoneNumber.RegistrationStatus.REGISTERED
    phone.last_error = ""
    phone.save(update_fields=["registration_status", "last_error", "updated_at"])


def sync_phone_number(phone: PhoneNumber, client: GraphClient | None = None) -> PhoneNumber:
    client = client or get_client(phone.waba.access_token)
    data = client.get_phone_number(phone.phone_number_id)
    apply_phone_data(phone, data)
    phone.last_synced_at = timezone.now()
    phone.save()
    return phone


def mark_reconnect_required(waba: WhatsAppBusinessAccount) -> None:
    waba.status = WhatsAppBusinessAccount.Status.DISCONNECTED
    waba.last_error = RECONNECT_REQUIRED
    waba.save(update_fields=["status", "last_error", "updated_at"])


def refresh_phone_number_now(phone: PhoneNumber) -> PhoneNumber:
    """Synchronous refresh for the API. Raises API errors."""
    waba = phone.waba
    if waba.status == WhatsAppBusinessAccount.Status.DISCONNECTED or not waba.access_token:
        raise Conflict("Reconnect this WhatsApp Business Account first.", code="waba_disconnected")
    try:
        return sync_phone_number(phone)
    except TokenInvalidError:
        mark_reconnect_required(waba)
        raise Conflict(
            "Meta no longer accepts this account's access. Reconnect it.", code="reconnect_required"
        ) from None
    except GraphAPIError as exc:
        raise _api_error(exc) from None


# --- Account management ------------------------------------------------------------------------


def ensure_connected(waba: WhatsAppBusinessAccount) -> None:
    if waba.status == WhatsAppBusinessAccount.Status.DISCONNECTED or not waba.access_token:
        raise Conflict("Reconnect this WhatsApp Business Account first.", code="waba_disconnected")


def resync_waba(waba: WhatsAppBusinessAccount) -> WhatsAppBusinessAccount:
    """Re-run onboarding: resubscribe webhooks, register pending numbers, refresh details."""
    ensure_connected(waba)
    with transaction.atomic():
        waba.subscribed_at = None
        waba.last_error = ""
        waba.save(update_fields=["subscribed_at", "last_error", "updated_at"])
        enqueue_finish_onboarding(waba)
    waba.refresh_from_db()
    return waba


def retry_registration(phone: PhoneNumber) -> PhoneNumber:
    ensure_connected(phone.waba)
    if phone.is_coexistence:
        raise Conflict(
            "Numbers shared with the WhatsApp Business app are not registered.",
            code="coexistence_number",
        )
    with transaction.atomic():
        if phone.registration_status != PhoneNumber.RegistrationStatus.REGISTERED:
            phone.registration_status = PhoneNumber.RegistrationStatus.PENDING
            phone.last_error = ""
            phone.save(update_fields=["registration_status", "last_error", "updated_at"])
        enqueue_finish_onboarding(phone.waba)
    phone.refresh_from_db()
    return phone


def set_default_phone_number(phone: PhoneNumber) -> PhoneNumber:
    if phone.waba.status == WhatsAppBusinessAccount.Status.DISCONNECTED:
        raise Conflict("Reconnect this WhatsApp Business Account first.", code="waba_disconnected")
    with transaction.atomic():
        list(
            PhoneNumber.objects.select_for_update()
            .filter(workspace_id=phone.workspace_id)
            .values_list("pk", flat=True)
        )
        PhoneNumber.objects.filter(workspace_id=phone.workspace_id, is_default=True).exclude(
            pk=phone.pk
        ).update(is_default=False, updated_at=timezone.now())
        PhoneNumber.objects.filter(pk=phone.pk).update(is_default=True, updated_at=timezone.now())
    phone.refresh_from_db()
    return phone


def disconnect_waba(waba: WhatsAppBusinessAccount) -> None:
    """Unsubscribe our app from the WABA's webhooks and forget the token."""
    if waba.access_token:
        try:
            get_client(waba.access_token).unsubscribe_app(waba.waba_id)
        except (TokenInvalidError, GraphPermissionError, InvalidParameterError):
            pass  # Access already revoked or the subscription is gone.
        except GraphAPIError as exc:
            raise _api_error(exc) from None
    with transaction.atomic():
        waba.status = WhatsAppBusinessAccount.Status.DISCONNECTED
        waba.access_token = ""
        waba.token_expires_at = None
        waba.subscribed_at = None
        waba.save(
            update_fields=[
                "status",
                "access_token",
                "token_expires_at",
                "subscribed_at",
                "updated_at",
            ]
        )
        waba.phone_numbers.filter(is_default=True).update(
            is_default=False, updated_at=timezone.now()
        )
