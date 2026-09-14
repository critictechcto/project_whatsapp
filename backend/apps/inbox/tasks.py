"""Inbox Celery tasks: dispatching queued messages to Meta and downloading inbound media."""

import copy
import logging
import mimetypes
from datetime import timedelta

from celery import shared_task
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.message_templates import services as template_services
from apps.whatsapp.client.errors import GraphAPIError, NetworkError

from . import limiter, sending, services
from .models import MediaAsset, Message

logger = logging.getLogger(__name__)

Status = Message.Status

MAX_SEND_RETRIES = 3
SEND_RETRY_COUNTDOWNS = (5, 30, 120)
MAX_MEDIA_RETRIES = 5
NETWORK_UNKNOWN = "network_unknown"
MEDIA_UNAVAILABLE = "media_unavailable"
INVALID_RESPONSE = "invalid_response"
# Meta keeps uploaded media for 30 days; re-upload a little earlier.
MEDIA_REUSE_MAX_AGE = timedelta(days=25)
STUCK_SENDING_AFTER = timedelta(minutes=15)
ERROR_MESSAGE_MAX_LENGTH = 1000


def _claim(message_id) -> bool:
    return (
        Message.objects.filter(pk=message_id, status=Status.QUEUED).update(
            status=Status.SENDING, updated_at=timezone.now()
        )
        == 1
    )


def _release(message: Message) -> None:
    """Give a claimed message back to the queue (it will be claimed again by a retry)."""
    Message.objects.filter(pk=message.pk, status=Status.SENDING).update(
        status=Status.QUEUED, updated_at=timezone.now()
    )


def _fail(message: Message, code: str, detail: str) -> bool:
    now = timezone.now()
    updated = Message.objects.filter(pk=message.pk, status=Status.SENDING).update(
        status=Status.FAILED,
        error_code=str(code)[:64],
        error_message=str(detail or "")[:ERROR_MESSAGE_MAX_LENGTH],
        failed_at=now,
        updated_at=now,
    )
    if updated:
        message.refresh_from_db()
        services.emit_delivery_updated(message, occurred_at=now)
    return bool(updated)


def _graph_error_code(exc: GraphAPIError) -> str:
    return str(exc.code) if exc.code is not None else "graph_error"


def _retry_or_fail(task, message: Message, exc: GraphAPIError) -> str:
    if exc.retryable and task.request.retries < task.max_retries:
        _release(message)
        index = min(task.request.retries, len(SEND_RETRY_COUNTDOWNS) - 1)
        countdown = exc.retry_after or SEND_RETRY_COUNTDOWNS[index]
        raise task.retry(exc=exc, countdown=countdown)
    _fail(message, _graph_error_code(exc), exc.message or type(exc).__name__)
    return Status.FAILED


@shared_task(bind=True, name="inbox.dispatch_message", max_retries=MAX_SEND_RETRIES)
def dispatch_message(self, message_id: str) -> str | None:
    """Send one queued message. Safe to run more than once: only the claimant sends."""
    if not _claim(message_id):
        logger.info("Message %s is not queued; skipping dispatch", message_id)
        return None
    message = Message.objects.select_related(
        "conversation__contact",
        "conversation__phone_number__waba",
        "template",
        "media_asset",
    ).get(pk=message_id)
    phone = message.conversation.phone_number

    try:
        sending.check_dispatch_policy(message)
    except sending.SendPolicyError as exc:
        _fail(message, exc.default_code, str(exc.detail))
        return Status.FAILED

    wait = limiter.get_limiter().acquire(phone.phone_number_id)
    if wait > 0:
        _release(message)
        dispatch_message.apply_async(args=[message_id], countdown=wait)
        return Status.QUEUED

    client = template_services.client_for(phone.waba)
    body = copy.deepcopy(message.payload)
    body["to"] = message.conversation.contact.wa_id

    if message.type in Message.MEDIA_TYPES:
        try:
            media_id = _meta_media_id(message.media_asset, phone.phone_number_id, client)
        except MediaUnavailable as exc:
            _fail(message, MEDIA_UNAVAILABLE, str(exc))
            return Status.FAILED
        except GraphAPIError as exc:  # nothing was sent yet, so network errors are retryable
            return _retry_or_fail(self, message, exc)
        body.setdefault(message.type, {})["id"] = media_id

    try:
        response = client.send_message(phone.phone_number_id, body)
    except NetworkError as exc:
        # The request may have reached Meta: retrying could send the message twice.
        _fail(message, NETWORK_UNKNOWN, f"Network error while sending; delivery is unknown. {exc}")
        return Status.FAILED
    except GraphAPIError as exc:
        return _retry_or_fail(self, message, exc)

    wamid = _wamid(response)
    now = timezone.now()
    if not wamid:
        _fail(message, INVALID_RESPONSE, "Meta accepted the request but returned no message id.")
        return Status.FAILED
    updated = Message.objects.filter(pk=message.pk, status=Status.SENDING).update(
        wamid=wamid,
        status=Status.SENT,
        sent_at=now,
        error_code="",
        error_message="",
        updated_at=now,
    )
    if updated:
        message.refresh_from_db()
        services.emit_delivery_updated(message, occurred_at=now)
    return Status.SENT


def _wamid(response) -> str | None:
    try:
        wamid = response["messages"][0]["id"]
    except (KeyError, IndexError, TypeError):
        return None
    return str(wamid) if wamid else None


class MediaUnavailable(Exception):
    pass


def _meta_media_id(asset: MediaAsset | None, phone_number_id: str, client) -> str:
    """Meta media id for ``asset`` on ``phone_number_id``, uploading when there is no fresh one."""
    if asset is None:
        raise MediaUnavailable("The media file was deleted.")
    now = timezone.now()
    if (
        asset.meta_media_id
        and asset.meta_phone_number_id == phone_number_id
        and asset.meta_uploaded_at
        and now - asset.meta_uploaded_at < MEDIA_REUSE_MAX_AGE
    ):
        return asset.meta_media_id
    if not asset.file:
        raise MediaUnavailable("The media file is missing.")
    try:
        with asset.file.open("rb") as handle:
            content = handle.read()
    except OSError as exc:
        raise MediaUnavailable("The media file could not be read.") from exc
    response = client.upload_media(
        phone_number_id, content=content, mime_type=asset.mime_type, filename=asset.file_name
    )
    media_id = str(response.get("id") or "")
    if not media_id:
        raise MediaUnavailable("Meta returned no media id for the upload.")
    MediaAsset.objects.filter(pk=asset.pk).update(
        meta_media_id=media_id,
        meta_phone_number_id=phone_number_id,
        meta_uploaded_at=now,
        updated_at=now,
    )
    return media_id


@shared_task(bind=True, name="inbox.download_media", max_retries=MAX_MEDIA_RETRIES)
def download_media(self, message_id: str) -> str | None:
    """Store an inbound message's media file. Meta's media URLs expire, so run promptly."""
    message = (
        Message.objects.select_related("conversation__phone_number__waba")
        .filter(pk=message_id)
        .first()
    )
    if message is None or message.file or not message.media_id:
        return None
    waba = message.conversation.phone_number.waba
    if not template_services.is_connected(waba):
        logger.info("Skipping media download for %s: account not connected", message.pk)
        return None
    client = template_services.client_for(waba)
    try:
        info = client.get_media(message.media_id)
        content = client.download_media(info["url"])
    except GraphAPIError as exc:
        if exc.retryable and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=30 * 2**self.request.retries) from exc
        logger.warning("Media download for message %s failed: %s", message.pk, exc)
        return None
    except (KeyError, TypeError):
        logger.warning("Media info for message %s has no URL", message.pk)
        return None

    mime_type = message.mime_type or str(info.get("mime_type") or "")
    extension = mimetypes.guess_extension(mime_type.split(";")[0].strip()) or ""
    name = message.file_name or f"{message.media_id}{extension}"
    message.file.save(name, ContentFile(content), save=False)
    updated = Message.objects.filter(pk=message.pk, file="").update(
        file=message.file.name,
        size=len(content),
        mime_type=mime_type,
        updated_at=timezone.now(),
    )
    if not updated:  # another run stored it first
        message.file.storage.delete(message.file.name)
        return None
    return message.file.name


@shared_task(name="inbox.fail_stuck_messages")
def fail_stuck_messages() -> int:
    """Mark messages stuck in ``sending`` (worker died mid-send) as failed with
    ``network_unknown``: Meta may or may not have received them, so they are not resent."""
    cutoff = timezone.now() - STUCK_SENDING_AFTER
    count = 0
    for message in Message.objects.filter(status=Status.SENDING, updated_at__lt=cutoff)[:500]:
        count += _fail(message, NETWORK_UNKNOWN, "Sending was interrupted; delivery is unknown.")
    if count:
        logger.warning("Marked %d stuck messages as failed", count)
    return count
