"""The refresh token lives only in an HttpOnly cookie scoped to ``/api/v1/auth/``.

Response bodies carry the access token alone, so script running in the dashboard can't read a
long-lived credential. The cookie endpoints (refresh, logout) add CSRF checks on top of
``SameSite=Strict``: a custom header that forces a CORS preflight, and an ``Origin`` allow-list.
"""

from django.conf import settings
from rest_framework import exceptions

REFRESH_COOKIE_NAME = "upchatz_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth/"
AUTH_HEADER = "X-UpChatz-Auth"


def _cookie_options() -> dict:
    return {
        "path": REFRESH_COOKIE_PATH,
        "domain": settings.AUTH_REFRESH_COOKIE_DOMAIN or None,
        "secure": settings.AUTH_REFRESH_COOKIE_SECURE,
        "httponly": True,
        "samesite": "Strict",
    }


def refresh_lifetime_seconds() -> int:
    return int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())


def set_refresh_cookie(response, refresh: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE_NAME, refresh, max_age=refresh_lifetime_seconds(), **_cookie_options()
    )


def clear_refresh_cookie(response) -> None:
    # Same attributes as when set, so the browser matches and drops the cookie.
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        "",
        max_age=0,
        expires="Thu, 01 Jan 1970 00:00:00 GMT",
        **_cookie_options(),
    )


def read_refresh_cookie(request) -> str | None:
    value = request.COOKIES.get(REFRESH_COOKIE_NAME)
    return value or None


def allowed_origins(request) -> set[str]:
    origins = {origin.rstrip("/") for origin in settings.CORS_ALLOWED_ORIGINS}
    if settings.FRONTEND_URL:
        origins.add(settings.FRONTEND_URL.rstrip("/"))
    # Same-origin requests (dashboard and API behind one domain) are never cross-site.
    origins.add(f"{request.scheme}://{request.get_host()}")
    return origins


def check_cookie_request(request) -> None:
    """CSRF guard for endpoints authenticated by the refresh cookie. Raises 403 on failure."""
    if request.headers.get(AUTH_HEADER) != "1":
        raise exceptions.PermissionDenied(
            f"The {AUTH_HEADER} header is required.", code="auth_header_required"
        )
    origin = request.headers.get("Origin")
    if origin and origin.rstrip("/") not in allowed_origins(request):
        raise exceptions.PermissionDenied("Origin not allowed.", code="origin_not_allowed")
