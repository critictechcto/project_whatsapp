import pytest
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions

from common.exceptions import (
    Conflict,
    FeatureNotAvailable,
    UpstreamUnavailable,
    api_exception_handler,
)

CONTEXT = {"view": None, "request": None}


def handle(exc):
    response = api_exception_handler(exc, CONTEXT)
    assert response is not None
    return response


def test_validation_error_envelope():
    response = handle(exceptions.ValidationError({"name": ["This field is required."]}))

    assert response.status_code == 400
    assert response.data == {
        "error": {
            "code": "invalid",
            "message": "Invalid input.",
            "details": {"name": ["This field is required."]},
        }
    }


def test_non_field_validation_error_keeps_list_details():
    response = handle(exceptions.ValidationError("Opt-in is required."))

    assert response.status_code == 400
    assert response.data["error"]["code"] == "invalid"
    assert response.data["error"]["details"] == ["Opt-in is required."]


@pytest.mark.parametrize("exc", [Http404(), Http404("No Contact matches the given query.")])
def test_django_http404_becomes_not_found(exc):
    response = handle(exc)

    assert response.status_code == 404
    assert response.data == {
        "error": {"code": "not_found", "message": "Not found.", "details": None}
    }


def test_drf_not_found():
    response = handle(exceptions.NotFound())

    assert response.status_code == 404
    assert response.data["error"]["code"] == "not_found"


def test_django_permission_denied():
    response = handle(DjangoPermissionDenied("internal reason"))

    assert response.status_code == 403
    assert response.data == {
        "error": {
            "code": "permission_denied",
            "message": "You do not have permission to perform this action.",
            "details": None,
        }
    }


def test_error_detail_with_custom_code():
    response = handle(exceptions.PermissionDenied("Upgrade your plan.", code="plan_limit"))

    assert response.status_code == 403
    assert response.data == {
        "error": {"code": "plan_limit", "message": "Upgrade your plan.", "details": None}
    }


def test_conflict():
    response = handle(Conflict())

    assert response.status_code == 409
    assert response.data == {
        "error": {
            "code": "conflict",
            "message": "The request conflicts with the current state of the resource.",
            "details": None,
        }
    }


def test_conflict_with_custom_message_and_code():
    response = handle(Conflict("Template name is taken.", code="duplicate_template"))

    assert response.status_code == 409
    assert response.data["error"] == {
        "code": "duplicate_template",
        "message": "Template name is taken.",
        "details": None,
    }


def test_upstream_unavailable():
    response = handle(UpstreamUnavailable())

    assert response.status_code == 503
    assert response.data["error"]["code"] == "upstream_unavailable"


def test_not_authenticated():
    response = handle(exceptions.NotAuthenticated())

    assert response.status_code == 401
    assert response.data["error"]["code"] == "not_authenticated"


def test_throttled_keeps_retry_after_header():
    response = handle(exceptions.Throttled(wait=5))

    assert response.status_code == 429
    assert response["Retry-After"] == "5"
    assert response.data["error"]["code"] == "throttled"


def test_structured_detail_without_error_detail_uses_defaults():
    response = handle(exceptions.APIException({"field": "bad"}))

    assert response.status_code == 500
    assert response.data == {
        "error": {
            "code": "error",
            "message": "A server error occurred.",
            "details": {"field": "bad"},
        }
    }


def test_feature_not_available_is_a_409_conflict():
    default = handle(FeatureNotAvailable())
    custom = handle(FeatureNotAvailable("Scheduling isn't included in your plan."))

    assert issubclass(FeatureNotAvailable, Conflict)
    assert default.status_code == custom.status_code == 409
    assert default.data["error"] == {
        "code": "feature_not_available",
        "message": "Your plan does not include this feature. Upgrade your plan to use it.",
        "details": None,
    }
    assert custom.data["error"]["code"] == "feature_not_available"
    assert custom.data["error"]["message"] == "Scheduling isn't included in your plan."


@pytest.mark.parametrize("exc", [ValueError("boom"), KeyError("missing"), RuntimeError()])
def test_non_api_exceptions_are_not_handled(exc):
    assert api_exception_handler(exc, CONTEXT) is None
