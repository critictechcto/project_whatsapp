"""Production settings. Every secret is required; the process refuses to start without them.

Required: DJANGO_SECRET_KEY, TOKEN_ENCRYPTION_KEYS, DJANGO_ALLOWED_HOSTS, DATABASE_URL, REDIS_URL
and WS_ALLOWED_ORIGINS. Importing these settings never connects to Postgres or Redis, so build
steps can use ``config.settings.build`` (placeholders, no secrets) for ``collectstatic``.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import SENTRY_DSN, env


def _require(name: str) -> str:
    value = env.str(name, default="").strip()
    if not value:
        raise ImproperlyConfigured(f"Set the {name} environment variable.")
    return value


DEBUG = False
SECRET_KEY = _require("DJANGO_SECRET_KEY")

TOKEN_ENCRYPTION_KEYS = [key for key in env.list("TOKEN_ENCRYPTION_KEYS", default=[]) if key]
if not TOKEN_ENCRYPTION_KEYS:
    raise ImproperlyConfigured("TOKEN_ENCRYPTION_KEYS must contain at least one Fernet key.")

_require("DJANGO_ALLOWED_HOSTS")
ALLOWED_HOSTS = [host for host in env.list("DJANGO_ALLOWED_HOSTS") if host]
# base.py falls back to local Postgres/Redis; production must point at the real services.
_require("DATABASE_URL")
_require("REDIS_URL")

# --- Behind the platform's HTTPS router -----------------------------------------------------
# The router terminates TLS and sets X-Forwarded-Proto. Host is passed through unchanged, so
# USE_X_FORWARDED_HOST stays off (it would let clients choose the host Django trusts). Health
# probes skip host validation and the redirect via common.health.HealthCheckMiddleware.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^healthz/$", r"^readyz/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# The refresh token cookie (apps.accounts.cookies) is HTTPS-only in production.
# Only an explicit false value turns it off; unset or empty stays Secure.
_refresh_cookie_secure = env.str("AUTH_REFRESH_COOKIE_SECURE", default="").strip().lower()
AUTH_REFRESH_COOKIE_SECURE = _refresh_cookie_secure not in {"0", "false", "no", "off"}
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True

STORAGES = {
    **STORAGES,  # noqa: F405 - media storage stays env-driven (MEDIA_STORAGE)
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

if MEDIA_STORAGE == "s3":  # noqa: F405
    _missing_storage = [
        name
        for name in ("AWS_STORAGE_BUCKET_NAME", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
        if not globals()[name]
    ]
    if _missing_storage:
        raise ImproperlyConfigured(
            "MEDIA_STORAGE=s3 requires " + ", ".join(_missing_storage) + " to be set."
        )

# Required explicitly: base.py would otherwise fall back to the local dev origin.
WS_ALLOWED_ORIGINS = [origin for origin in env.list("WS_ALLOWED_ORIGINS", default=[]) if origin]
if not WS_ALLOWED_ORIGINS:
    raise ImproperlyConfigured("WS_ALLOWED_ORIGINS must list the dashboard origin(s).")

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        send_default_pii=False,
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0),
        environment=env("SENTRY_ENVIRONMENT", default="production"),
    )
