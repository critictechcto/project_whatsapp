"""Production settings. Every secret is required; the process refuses to start without them."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import SENTRY_DSN, env

DEBUG = False
SECRET_KEY = env("DJANGO_SECRET_KEY")

TOKEN_ENCRYPTION_KEYS = env.list("TOKEN_ENCRYPTION_KEYS")
if not TOKEN_ENCRYPTION_KEYS:
    raise ImproperlyConfigured("TOKEN_ENCRYPTION_KEYS must contain at least one Fernet key.")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^healthz/$", r"^readyz/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True

STORAGES = {
    **STORAGES,  # noqa: F405 - media storage stays env-driven (MEDIA_STORAGE_BACKEND)
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

if not WS_ALLOWED_ORIGINS:  # noqa: F405
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
