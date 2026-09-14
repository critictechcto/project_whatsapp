"""Meta webhook callback (``/webhooks/meta/``).

A plain Django view (not DRF) so the raw body reaches signature verification untouched; it is not
part of the OpenAPI schema. POST only verifies, stores and enqueues; processing happens in
``webhooks.process_event``.
"""

import hashlib
import hmac
import json
import logging
import re

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import WebhookEvent
from .tasks import enqueue_on_commit

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-Hub-Signature-256"
_SIGNATURE_RE = re.compile(r"sha256=([0-9a-fA-F]{64})")


@csrf_exempt
@require_http_methods(["GET", "POST"])
def meta_callback(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        return _verify_subscription(request)
    return _receive(request)


def _verify_subscription(request: HttpRequest) -> HttpResponse:
    expected = getattr(settings, "META_WEBHOOK_VERIFY_TOKEN", "") or ""
    mode = request.GET.get("hub.mode", "")
    token = request.GET.get("hub.verify_token", "")
    if mode == "subscribe" and expected and hmac.compare_digest(token.encode(), expected.encode()):
        return HttpResponse(request.GET.get("hub.challenge", ""), content_type="text/plain")
    logger.warning("Meta webhook verification rejected (mode=%r)", mode)
    return HttpResponse("Forbidden", status=403, content_type="text/plain")


def signature_is_valid(body: bytes, header: str | None, secret: str) -> bool:
    """``header`` must be ``sha256=<hex HMAC-SHA256 of body keyed with the app secret>``."""
    if not secret or not header:
        return False
    match = _SIGNATURE_RE.fullmatch(header.strip())
    if match is None:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(match.group(1).lower().encode(), expected.encode())


def _receive(request: HttpRequest) -> HttpResponse:
    secret = getattr(settings, "META_APP_SECRET", "") or ""
    if not secret:
        logger.error("META_APP_SECRET is not configured; rejecting Meta webhook")
    body = request.body
    if not signature_is_valid(body, request.headers.get(SIGNATURE_HEADER), secret):
        logger.warning("Meta webhook with missing or invalid signature rejected")
        return HttpResponse("Invalid signature", status=401, content_type="text/plain")

    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, ValueError):
        return HttpResponse("Invalid JSON", status=400, content_type="text/plain")
    if not isinstance(payload, dict):
        return HttpResponse("Invalid JSON", status=400, content_type="text/plain")

    digest = hashlib.sha256(body).hexdigest()
    object_type = payload.get("object")
    with transaction.atomic():
        event, created = WebhookEvent.objects.get_or_create(
            body_sha256=digest,
            defaults={
                "payload": payload,
                "object_type": object_type[:64] if isinstance(object_type, str) else "",
            },
        )
        if created:
            enqueue_on_commit(event.pk)
        else:
            logger.info("Duplicate Meta webhook delivery %s ignored", digest[:12])
    return HttpResponse("OK", content_type="text/plain")
