"""Settings shared by every environment.

Values come from environment variables, falling back to the repo-root ``.env`` file.
Apps must read their settings from here; declare new ones in this file (lead-owned).
"""

from datetime import timedelta
from pathlib import Path

import environ

from common.enum_overrides import AppEnumNameOverrides

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
    "apps.analytics",
    "apps.developer_api",
]
# daphne first so `runserver` serves ASGI (HTTP + WebSockets).
INSTALLED_APPS = ["daphne", *DJANGO_APPS, *THIRD_PARTY_APPS, *LOCAL_APPS]

MIDDLEWARE = [
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
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    },
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
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
MEDIA_ROOT = BASE_DIR / "media"

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

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
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

# --- Billing (Razorpay) ---------------------------------------------------------------------

RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", default="")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", default="")

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
