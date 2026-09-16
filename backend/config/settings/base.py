"""Settings shared by every environment.

Values come from environment variables, falling back to the repo-root ``.env`` file.
Apps must read their settings from here; declare new ones in this file (lead-owned).
"""

from datetime import timedelta
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

from common.enum_overrides import AppEnumNameOverrides
from common.redis_tls import redis_ssl_options

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
REPO_ROOT = BASE_DIR.parent

env = environ.Env()
if (REPO_ROOT / ".env").exists():
    environ.Env.read_env(REPO_ROOT / ".env")

# --- Core ---------------------------------------------------------------------------------

SECRET_KEY = env("DJANGO_SECRET_KEY", default="")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]
THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "django_celery_beat",
    "channels",
]
LOCAL_APPS = [
    "common",
    "apps.accounts",
    "apps.tenants",
    "apps.whatsapp",
    "apps.message_templates",
    "apps.contacts",
    "apps.campaigns",
    "apps.inbox",
    "apps.automations",
    "apps.webhooks",
    "apps.billing",
    "apps.catalog",
    "apps.orders",
    "apps.payments",
    "apps.shop",
    "apps.seller_alerts",
    "apps.analytics",
    "apps.developer_api",
]
# daphne first so `runserver` serves ASGI (HTTP + WebSockets).
INSTALLED_APPS = ["daphne", *DJANGO_APPS, *THIRD_PARTY_APPS, *LOCAL_APPS]

MIDDLEWARE = [
    # First: health probes skip ALLOWED_HOSTS and the HTTPS redirect (see common/health.py).
    "common.health.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Data stores ----------------------------------------------------------------------------

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://upchatz:upchatz@localhost:5433/upchatz",
    ),
}
# Query parameters in the URL (e.g. ``?sslmode=require``) become connection OPTIONS.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
# Set true when connecting through PgBouncer in transaction pooling mode: server-side cursors
# (used by QuerySet.iterator()) can't survive across pooled transactions. iterator() still works,
# it just fetches each result set in one go.
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = env.bool(
    "DATABASE_DISABLE_SERVER_SIDE_CURSORS", default=False
)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# One Redis for cache, channel layer and Celery broker. A ``rediss://`` URL turns on TLS with
# certificate verification for each of them (common.redis_tls). The inbox send limiter builds its
# own client from REDIS_URL; redis-py verifies rediss:// certificates by default there too.
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
# Escape hatches for managed Redis whose certificate isn't in the system trust store: a CA bundle
# path, or the verification level (required | optional | none). Keep "required" in production.
REDIS_SSL_CA_CERTS = env("REDIS_SSL_CA_CERTS", default="")
REDIS_SSL_CERT_REQS = env("REDIS_SSL_CERT_REQS", default="required")
REDIS_SSL_OPTIONS = redis_ssl_options(
    REDIS_URL, cert_reqs=REDIS_SSL_CERT_REQS, ca_certs=REDIS_SSL_CA_CERTS
)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {**REDIS_SSL_OPTIONS},
    },
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [{"address": REDIS_URL, **REDIS_SSL_OPTIONS}]},
    },
}

# --- Auth -----------------------------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- I18N -----------------------------------------------------------------------------------

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# --- Static files ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = env.path("MEDIA_ROOT", default=BASE_DIR / "media")

# Uploads (contact imports, inbox media, product images). MEDIA_STORAGE picks where they live:
# - "local" (default): FileSystemStorage under MEDIA_ROOT. Development only: the API, worker and
#   beat containers do not share a disk in production.
# - "s3": one S3-compatible bucket (DigitalOcean Spaces) shared by every process. `default` is
#   private with signed URLs valid for AWS_QUERYSTRING_EXPIRE seconds; `public_media` holds
#   product images as public-read objects, linked from PUBLIC_MEDIA_BASE_URL when set, else
#   https://AWS_S3_CUSTOM_DOMAIN when set, else the bucket URL. See common/storage.py.
MEDIA_STORAGE = env("MEDIA_STORAGE", default="local").strip().lower()
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="")
# e.g. https://blr1.digitaloceanspaces.com and blr1
AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default="") or None
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="") or None
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")
# Optional CDN host without scheme (e.g. media.upchatz.com); used for public product images only.
AWS_S3_CUSTOM_DOMAIN = env("AWS_S3_CUSTOM_DOMAIN", default="") or None
AWS_QUERYSTRING_EXPIRE = env.int("AWS_QUERYSTRING_EXPIRE", default=3600)
AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_S3_ADDRESSING_STYLE = "virtual"
# Objects above this size spool to a temp file instead of memory while being read.
AWS_S3_MAX_MEMORY_SIZE = 5 * 1024 * 1024

if MEDIA_STORAGE == "local":
    _MEDIA_STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}}
elif MEDIA_STORAGE == "s3":
    _MEDIA_STORAGES = {
        "default": {"BACKEND": "common.storage.PrivateMediaStorage"},
        "public_media": {
            "BACKEND": "common.storage.PublicMediaStorage",
            "OPTIONS": {"custom_domain": AWS_S3_CUSTOM_DOMAIN},
        },
    }
else:
    raise ImproperlyConfigured(f"MEDIA_STORAGE must be 'local' or 's3', not {MEDIA_STORAGE!r}.")

STORAGES = {
    **_MEDIA_STORAGES,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# --- API ------------------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_SCHEMA_CLASS": "common.schema.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "common.pagination.DefaultCursorPagination",
    "PAGE_SIZE": 50,
    "EXCEPTION_HANDLER": "common.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "auth": "20/min",
        "webhooks": "600/min",
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "UpChatz API",
    "DESCRIPTION": "Multi-tenant WhatsApp Business Platform (Cloud API) for Indian businesses.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    # Each app may define ENUM_NAME_OVERRIDES in `apps/<app>/schema_enums.py`.
    "ENUM_NAME_OVERRIDES": AppEnumNameOverrides(),
    # The fallback hook lets value-only overrides also name fields whose choices carry labels.
    "POSTPROCESSING_HOOKS": [
        "common.enum_overrides.postprocess_enum_value_fallback",
        "drf_spectacular.hooks.postprocess_schema_enums",
    ],
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:5173"])
CORS_ALLOW_HEADERS = (
    "accept",
    "authorization",
    "content-type",
    "idempotency-key",
    "x-requested-with",
    "x-workspace-id",
)

FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:5173")

# --- Celery ---------------------------------------------------------------------------------
# Beat entries are collected from each app's optional `schedules.py` (see config/celery.py).

# Empty or unset = REDIS_URL (an empty value would otherwise make Celery fall back to AMQP).
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="") or REDIS_URL
# Without this kombu connects to rediss:// with CERT_NONE; None keeps plain redis:// as is.
CELERY_BROKER_USE_SSL = (
    redis_ssl_options(CELERY_BROKER_URL, cert_reqs=REDIS_SSL_CERT_REQS, ca_certs=REDIS_SSL_CA_CERTS)
    or None
)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 3600}
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_SOFT_TIME_LIMIT = 240
CELERY_TASK_TIME_LIMIT = 300
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_ALWAYS_EAGER = False

# --- Meta / WhatsApp Cloud API --------------------------------------------------------------

META_APP_ID = env("META_APP_ID", default="")
META_APP_SECRET = env("META_APP_SECRET", default="")
META_EMBEDDED_SIGNUP_CONFIG_ID = env("META_EMBEDDED_SIGNUP_CONFIG_ID", default="")
META_GRAPH_API_VERSION = env("META_GRAPH_API_VERSION", default="v24.0")
META_GRAPH_BASE_URL = env("META_GRAPH_BASE_URL", default="https://graph.facebook.com")
META_GRAPH_TIMEOUT_SECONDS = env.float("META_GRAPH_TIMEOUT_SECONDS", default=30.0)
META_WEBHOOK_VERIFY_TOKEN = env("META_WEBHOOK_VERIFY_TOKEN", default="")

# Dotted path of the GraphClient implementation returned by apps.whatsapp.client.get_client().
WHATSAPP_GRAPH_CLIENT = env(
    "WHATSAPP_GRAPH_CLIENT", default="apps.whatsapp.client.graph.HttpGraphClient"
)

# Fernet keys (comma-separated) for customer tokens. The first key encrypts; all keys decrypt.
TOKEN_ENCRYPTION_KEYS = env.list("TOKEN_ENCRYPTION_KEYS", default=[])

DEFAULT_PHONE_REGION = "IN"

# --- App limits -----------------------------------------------------------------------------

INVITATION_TTL_DAYS = env.int("INVITATION_TTL_DAYS", default=7)
WEBHOOK_EVENT_RETENTION_DAYS = env.int("WEBHOOK_EVENT_RETENTION_DAYS", default=30)
CONTACT_IMPORT_MAX_BYTES = env.int("CONTACT_IMPORT_MAX_BYTES", default=10 * 1024 * 1024)
CONTACT_IMPORT_MAX_ROWS = env.int("CONTACT_IMPORT_MAX_ROWS", default=100_000)

# Recipients materialised or dispatched per Celery batch while a campaign runs.
CAMPAIGN_BATCH_SIZE = env.int("CAMPAIGN_BATCH_SIZE", default=100)

# Upload caps for WhatsApp media assets by Meta media type (limits set by Meta).
WHATSAPP_MEDIA_MAX_BYTES = {
    "image": 5 * 1024 * 1024,
    "video": 16 * 1024 * 1024,
    "audio": 16 * 1024 * 1024,
    "document": 100 * 1024 * 1024,
    "sticker": 500 * 1024,
}

# Per-message cost in INR by template category, used only for estimates shown before a campaign
# launches (under Meta's current pricing for India). Meta bills the WABA and may change rates.
# Keys are MessageTemplate.Category values; values are decimal strings.
WHATSAPP_RATE_CARD_INR = {
    "MARKETING": env("WHATSAPP_RATE_MARKETING_INR", default="0.7846"),
    "UTILITY": env("WHATSAPP_RATE_UTILITY_INR", default="0.1150"),
    "AUTHENTICATION": env("WHATSAPP_RATE_AUTHENTICATION_INR", default="0.1150"),
    "SERVICE": env("WHATSAPP_RATE_SERVICE_INR", default="0"),
}

# --- Realtime (Channels) --------------------------------------------------------------------

# Seconds a single-use ticket from POST /api/v1/inbox/ws-ticket/ stays valid.
WS_TICKET_TTL = env.int("WS_TICKET_TTL", default=30)
# Browser origins allowed to open /ws/v1/ (the dashboard). Defaults to the CORS origins.
WS_ALLOWED_ORIGINS = env.list("WS_ALLOWED_ORIGINS", default=CORS_ALLOWED_ORIGINS)

# --- Billing (Razorpay) ---------------------------------------------------------------------

RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", default="")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", default="")
# Razorpay plan ids by plan slug and interval, as JSON:
#   {"starter": {"monthly": "plan_...", "annual": "plan_..."}, "growth": {...}, "pro": {...}}
RAZORPAY_PLAN_IDS = env.json("RAZORPAY_PLAN_IDS", default={})

# Seller details printed on GST tax invoices. The seller state code decides CGST+SGST vs IGST.
BILLING_SELLER_LEGAL_NAME = env("BILLING_SELLER_LEGAL_NAME", default="")
BILLING_SELLER_GSTIN = env("BILLING_SELLER_GSTIN", default="")
BILLING_SELLER_STATE_CODE = env("BILLING_SELLER_STATE_CODE", default="")
BILLING_SELLER_ADDRESS = env("BILLING_SELLER_ADDRESS", default="")
# SAC 998314: information technology design and development services (SaaS subscriptions).
BILLING_SAC_CODE = env("BILLING_SAC_CODE", default="998314")
BILLING_GST_RATE_PERCENT = env.int("BILLING_GST_RATE_PERCENT", default=18)
# Seconds before a Razorpay API call (checkout, cancel, fetch) times out.
RAZORPAY_TIMEOUT = env.float("RAZORPAY_TIMEOUT", default=20.0)

# --- Commerce (sell on WhatsApp) ------------------------------------------------------------

# Absolute base URL of this API as the internet sees it; builds the per-seller Razorpay webhook
# URLs shown in the dashboard.
PUBLIC_API_BASE_URL = env("PUBLIC_API_BASE_URL", default="http://localhost:8000")
# Absolute public base URL for product images (a CDN or public bucket). Meta fetches catalog
# images from it, so it must be reachable over HTTPS from the internet. Empty = serve MEDIA_URL
# from PUBLIC_API_BASE_URL.
PUBLIC_MEDIA_BASE_URL = env("PUBLIC_MEDIA_BASE_URL", default="")
# Razorpay payment link lifetime, and the local deadline after which an unpaid checkout expires
# and releases its stock (kept a few minutes longer than the link).
PAYMENT_LINK_EXPIRY_MINUTES = env.int("PAYMENT_LINK_EXPIRY_MINUTES", default=30)
ORDER_CHECKOUT_TTL_MINUTES = env.int("ORDER_CHECKOUT_TTL_MINUTES", default=35)

# UpChatz's own WhatsApp number that sends order alerts to sellers' personal numbers. Lives in
# the UpChatz WABA (not a seller's); empty disables seller alerts.
PLATFORM_WA_WABA_ID = env("PLATFORM_WA_WABA_ID", default="")
PLATFORM_WA_PHONE_NUMBER_ID = env("PLATFORM_WA_PHONE_NUMBER_ID", default="")
PLATFORM_WA_DISPLAY_PHONE_NUMBER = env("PLATFORM_WA_DISPLAY_PHONE_NUMBER", default="")
# System-user token for the UpChatz WABA. Secret: never log or serialize it.
PLATFORM_WA_ACCESS_TOKEN = env("PLATFORM_WA_ACCESS_TOKEN", default="")

# --- Email ----------------------------------------------------------------------------------

EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="UpChatz <no-reply@upchatz.com>")

# --- Observability --------------------------------------------------------------------------

SENTRY_DSN = env("SENTRY_DSN", default="")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "default"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "httpx": {"level": "WARNING"},
        "httpcore": {"level": "WARNING"},
    },
}
