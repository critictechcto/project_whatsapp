"""Payments API, the buyer return page and the optional per-seller gateway webhook
(docs/contracts/wave-3-commerce.md, "Payments")."""

import logging
import re
import time
import uuid

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.html import escape
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from apps.orders.models import StoreSettings
from common.exceptions import UpstreamUnavailable
from common.roles import Role
from common.tenancy import WorkspaceScopedGenericViewSet

from . import services
from .exceptions import PaymentAccountInvalid, PaymentAccountMissing, PaymentProviderError
from .models import PaymentAccount, PaymentLink, new_webhook_token
from .providers import InvalidWebhookSignature, get_provider
from .schema_enums import PAYMENT_LINK_STATUSES
from .serializers import PaymentAccountSerializer, PaymentLinkSerializer

logger = logging.getLogger(__name__)

RETURN_PAGE_RATE_PER_MINUTE = 30
PENDING_REFRESH_SECONDS = 15


class PaymentAccountViewSet(WorkspaceScopedGenericViewSet):
    """The workspace's own payment gateway account (Razorpay or Cashfree). Secrets are never
    returned."""

    queryset = PaymentAccount.objects.all()
    serializer_class = PaymentAccountSerializer
    filter_backends: list = []
    read_role = Role.ADMIN
    write_role = Role.ADMIN
    action_roles = {"destroy": Role.OWNER}

    @extend_schema(operation_id="payments_account_retrieve", responses=PaymentAccountSerializer)
    def retrieve(self, request):
        account = services.get_account(self.workspace) or PaymentAccount(workspace=self.workspace)
        return Response(PaymentAccountSerializer(account).data)

    @extend_schema(
        operation_id="payments_account_partial_update",
        request=PaymentAccountSerializer,
        responses=PaymentAccountSerializer,
        description=(
            "Changing the provider clears keys and secrets; changing a key, secret or mode "
            "resets status to unverified. Razorpay key ids set the mode (400 on mode when a "
            "given mode disagrees); Cashfree needs a mode (400 on mode); webhook_secret is "
            "Razorpay only."
        ),
    )
    def partial_update(self, request):
        serializer = PaymentAccountSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        account = services.update_account(self.workspace, serializer.validated_data)
        return Response(PaymentAccountSerializer(account).data)

    @extend_schema(operation_id="payments_account_destroy", responses={204: None})
    def destroy(self, request):
        PaymentAccount.objects.filter(workspace=self.workspace).delete()
        return Response(status=204)

    @extend_schema(
        operation_id="payments_account_verify_create",
        request=None,
        responses=PaymentAccountSerializer,
        description=(
            "One authenticated read call on the gateway. 409 payment_account_missing or "
            "payment_account_invalid; 503 upstream_unavailable when the gateway can't be "
            "reached."
        ),
    )
    def verify(self, request):
        account = services.get_account(self.workspace)
        if account is None or not account.key_id or not account.key_secret:
            raise PaymentAccountMissing()
        if not account.mode:
            raise serializers.ValidationError(
                {"mode": ["Choose test (sandbox) or live mode before verifying."]}
            )
        try:
            account = services.verify_account(account)
        except PaymentProviderError:
            raise UpstreamUnavailable(
                "We couldn't reach your payment gateway. Try again shortly."
            ) from None
        return Response(PaymentAccountSerializer(account).data)

    @extend_schema(
        operation_id="payments_account_rotate_webhook_create",
        request=None,
        responses=PaymentAccountSerializer,
        description=(
            "Issue a new optional webhook URL; update it in the gateway afterwards. "
            "409 payment_account_missing when no account is saved."
        ),
    )
    def rotate_webhook(self, request):
        account = services.get_account(self.workspace)
        if account is None:
            raise PaymentAccountMissing()
        account.webhook_token = new_webhook_token()
        account.save(update_fields=["webhook_token", "updated_at"])
        return Response(PaymentAccountSerializer(account).data)


class PaymentLinkViewSet(WorkspaceScopedGenericViewSet):
    queryset = PaymentLink.objects.all()
    serializer_class = PaymentLinkSerializer
    filter_backends: list = []
    read_role = Role.VIEWER
    write_role = Role.ADMIN

    @extend_schema(
        operation_id="payments_links_list",
        parameters=[
            OpenApiParameter("order", OpenApiTypes.UUID),
            OpenApiParameter("status", OpenApiTypes.STR, enum=PAYMENT_LINK_STATUSES),
        ],
        responses=PaymentLinkSerializer(many=True),
    )
    def list(self, request):
        queryset = self.get_queryset()
        if order := request.query_params.get("order"):
            try:
                queryset = queryset.filter(order_id=uuid.UUID(order))
            except ValueError:
                raise serializers.ValidationError({"order": ["Must be a valid UUID."]}) from None
        if status := request.query_params.get("status"):
            if status not in PAYMENT_LINK_STATUSES:
                raise serializers.ValidationError(
                    {"status": [f"Use one of: {', '.join(PAYMENT_LINK_STATUSES)}."]}
                )
            queryset = queryset.filter(status=status)
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(PaymentLinkSerializer(page, many=True).data)


# --- Optional merchant webhook ---------------------------------------------------------------


def _error(code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse(
        {"error": {"code": code, "message": message, "details": None}}, status=status
    )


@csrf_exempt
@require_POST
def merchant_webhook(request: HttpRequest, token: str) -> JsonResponse:
    """``POST /webhooks/payments/merchants/<token>/`` (public, optional, not in the schema).

    404 for an unknown token, 400 for a bad signature, otherwise always 200: polling still
    confirms any link whose update couldn't be applied here.
    """
    account = PaymentAccount.objects.filter(webhook_token=token).first()
    if account is None:
        return _error("not_found", "Not found.", 404)
    try:
        services.handle_merchant_webhook(account, request.headers, request.body)
    except (InvalidWebhookSignature, PaymentAccountMissing):
        return _error("invalid_signature", "Invalid webhook signature.", 400)
    except Exception:
        logger.exception("Merchant webhook for workspace %s crashed", account.workspace_id)
    return JsonResponse({"status": "ok"})


# --- Buyer return page -----------------------------------------------------------------------


def _throttled(request: HttpRequest) -> bool:
    ip = request.META.get("REMOTE_ADDR", "") or "unknown"
    key = f"payments:return:{ip}:{int(time.time() // 60)}"
    if cache.add(key, 1, timeout=90):
        return False
    try:
        count = cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, timeout=90)
        count = 1
    return count > RETURN_PAGE_RATE_PER_MINUTE


def format_inr(paise: int) -> str:
    """``123456789`` → ``₹12,34,567.89`` (Indian digit grouping)."""
    rupees, rest = divmod(int(paise), 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join([*groups, tail])
    return f"₹{digits}.{rest:02d}"


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
{refresh}<title>{title}</title>
<style>
body{{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:#f6f5f1;
color:#1c1b19;display:flex;min-height:100vh;align-items:center;justify-content:center;padding:16px}}
main{{background:#fff;border:1px solid #e3e0d8;border-radius:12px;max-width:420px;width:100%;
padding:28px 24px;box-sizing:border-box}}
.store{{font-size:13px;color:#6b675e;margin:0 0 12px}}
h1{{font-size:22px;line-height:1.25;margin:0 0 10px;letter-spacing:-0.01em}}
p{{font-size:16px;line-height:1.5;margin:0 0 18px}}
.amount{{font-weight:600}}
a.button{{display:block;text-align:center;background:#128c4a;color:#fff;text-decoration:none;
font-weight:600;padding:14px 16px;border-radius:8px;font-size:16px}}
</style>
</head>
<body>
<main>
{store}<h1>{title}</h1>
<p>{message}</p>
{amount}{button}</main>
</body>
</html>
"""


def _page(
    status: int,
    *,
    title: str,
    message: str,
    store_name: str = "",
    amount: str = "",
    wa_link: str = "",
    refresh: bool = False,
) -> HttpResponse:
    html = _PAGE.format(
        title=escape(title),
        message=escape(message),
        store=f'<p class="store">{escape(store_name)}</p>\n' if store_name else "",
        amount=f'<p class="amount">{escape(amount)}</p>\n' if amount else "",
        button=(
            f'<a class="button" href="{escape(wa_link)}">Back to WhatsApp</a>\n' if wa_link else ""
        ),
        refresh=(
            f'<meta http-equiv="refresh" content="{PENDING_REFRESH_SECONDS}">\n' if refresh else ""
        ),
    )
    response = HttpResponse(html, status=status, content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex"
    response["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; "
        "frame-ancestors 'none'"
    )
    return response


def _check_callback_signature(request: HttpRequest, link: PaymentLink) -> None:
    """Log whether Razorpay's callback signature matches. Never trusted: we re-fetch anyway."""
    if link.provider != PaymentAccount.Provider.RAZORPAY or "razorpay_signature" not in request.GET:
        return
    account = PaymentAccount.objects.filter(workspace_id=link.workspace_id).first()
    if account is None:
        return
    provider = get_provider(account)
    checker = getattr(provider, "callback_signature_is_valid", None)
    if checker is not None and not checker(request.GET):
        logger.warning("Razorpay callback signature mismatch for payment link %s", link.pk)


@require_GET
def payment_return(request: HttpRequest, payment_link_id: uuid.UUID) -> HttpResponse:
    """``GET /pay/return/<payment_link_id>/`` (public, browser-facing, not in the schema).

    The gateway sends the buyer here after paying. Query parameters are never trusted: the link
    is refreshed from the gateway. Throttled per IP; gateway errors still render the
    "confirming" page.
    """
    if _throttled(request):
        return _page(429, title="Too many requests", message="Please wait a minute and try again.")
    link = PaymentLink.objects.filter(pk=payment_link_id).first()
    if link is None:
        return _page(404, title="Link not found", message="This payment link doesn't exist.")

    try:
        _check_callback_signature(request, link)
        link = services.refresh_payment_link(link)
    except (PaymentProviderError, PaymentAccountMissing, PaymentAccountInvalid) as exc:
        logger.warning("Return page could not refresh payment link %s: %s", link.pk, exc)
    except Exception:
        logger.exception("Return page could not refresh payment link %s", link.pk)

    order = link.order
    store_name = (
        StoreSettings.objects.filter(workspace_id=link.workspace_id)
        .values_list("store_name", flat=True)
        .first()
        or link.workspace.name
    )
    phone = order.phone_number
    digits = re.sub(r"\D", "", phone.phone_e164 or phone.display_phone_number or "")
    common = {
        "store_name": store_name,
        "amount": format_inr(link.amount_paise),
        "wa_link": f"https://wa.me/{digits}" if digits else "",
    }
    if link.status == PaymentLink.Status.PAID:
        return _page(
            200,
            title="Payment received",
            message=f"Payment received for order {order.number}. You can go back to WhatsApp.",
            **common,
        )
    if link.status in (
        PaymentLink.Status.EXPIRED,
        PaymentLink.Status.CANCELLED,
        PaymentLink.Status.FAILED,
    ):
        return _page(
            200,
            title="This payment link is no longer active",
            message=(
                f"Payment for order {order.number} wasn't completed with this link. "
                "Go back to WhatsApp to continue."
            ),
            **common,
        )
    return _page(
        200,
        title="We're confirming your payment…",
        message=(
            f"This usually takes a minute. We'll message you on WhatsApp about order "
            f"{order.number} as soon as it's confirmed."
        ),
        refresh=True,
        **common,
    )
