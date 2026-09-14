"""Test settings. Must work without a .env file and never reach real external services."""

import base64
import re

from .base import *  # noqa: F403
from .base import DATABASES, MIDDLEWARE, REPO_ROOT, REST_FRAMEWORK

SECRET_KEY = "test-secret-key-not-for-production"
DEBUG = False

MIDDLEWARE = [m for m in MIDDLEWARE if not m.startswith("whitenoise.")]

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

CELERY_BROKER_URL = "memory://"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": dict.fromkeys(REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/min"),
}

TOKEN_ENCRYPTION_KEYS = [base64.urlsafe_b64encode(b"upchatz-test-key-000000000000000").decode()]

META_APP_ID = "1234567890"
META_APP_SECRET = "test-app-secret"
META_EMBEDDED_SIGNUP_CONFIG_ID = "test-config-id"
META_GRAPH_API_VERSION = "v24.0"
META_GRAPH_BASE_URL = "https://graph.facebook.com"
META_WEBHOOK_VERIFY_TOKEN = "test-verify-token"
WHATSAPP_GRAPH_CLIENT = "apps.whatsapp.client.fake.FakeGraphClient"

RAZORPAY_KEY_ID = "rzp_test_key"
RAZORPAY_KEY_SECRET = "rzp-test-secret"
RAZORPAY_WEBHOOK_SECRET = "rzp-test-webhook-secret"
RAZORPAY_PLAN_IDS = {
    slug: {"monthly": f"plan_test_{slug}_monthly", "annual": f"plan_test_{slug}_annual"}
    for slug in ("starter", "growth", "pro")
}
BILLING_SELLER_LEGAL_NAME = "UpChatz Test Seller Private Limited"
# Sample Karnataka GSTIN with a valid check character (matches BILLING_SELLER_STATE_CODE).
BILLING_SELLER_GSTIN = "29ABCDE1234F1ZW"
BILLING_SELLER_STATE_CODE = "29"
BILLING_SELLER_ADDRESS = "1 Test Road, Bengaluru, Karnataka 560001"

PUBLIC_API_BASE_URL = "https://api.testserver"
PUBLIC_MEDIA_BASE_URL = "https://media.testserver"
PAYMENT_LINK_EXPIRY_MINUTES = 30
ORDER_CHECKOUT_TTL_MINUTES = 35
PLATFORM_WA_WABA_ID = "990000000000001"
PLATFORM_WA_PHONE_NUMBER_ID = "990000000000002"
PLATFORM_WA_DISPLAY_PHONE_NUMBER = "+91 80000 00001"
PLATFORM_WA_ACCESS_TOKEN = "EAAG-test-platform-token"

SENTRY_DSN = ""
FRONTEND_URL = "http://testserver-frontend"
WS_ALLOWED_ORIGINS = [FRONTEND_URL]
WS_TICKET_TTL = 30

# Each git worktree gets its own test database so parallel agents never collide.
_checkout = re.sub(r"[^a-z0-9]+", "_", REPO_ROOT.name.lower()).strip("_") or "main"
DATABASES["default"]["TEST"] = {"NAME": f"test_upchatz_{_checkout}"[:63]}

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
