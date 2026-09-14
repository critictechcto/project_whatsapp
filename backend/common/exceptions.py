"""API error envelope: every error response is ``{"error": {"code", "message", "details"}}``."""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions
from rest_framework.views import exception_handler


class Conflict(exceptions.APIException):
    status_code = 409
    default_code = "conflict"
    default_detail = "The request conflicts with the current state of the resource."


class UpstreamUnavailable(exceptions.APIException):
    status_code = 503
    default_code = "upstream_unavailable"
    default_detail = "A required upstream service is unavailable. Try again shortly."


def api_exception_handler(exc, context):
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        return None
    response.data = {"error": _error_body(exc, response.data)}
    return response


def _error_body(exc, data) -> dict:
    if isinstance(exc, exceptions.ValidationError):
        return {"code": "invalid", "message": "Invalid input.", "details": data}

    detail = getattr(exc, "detail", None)
    if isinstance(detail, exceptions.ErrorDetail):
        return {"code": detail.code or "error", "message": str(detail), "details": None}

    return {
        "code": getattr(exc, "default_code", "error"),
        "message": str(getattr(exc, "default_detail", "Request failed.")),
        "details": data,
    }
