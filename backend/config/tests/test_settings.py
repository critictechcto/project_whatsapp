import os
import re

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection

from apps.whatsapp.client import get_client
from apps.whatsapp.client.fake import FakeGraphClient
from common.crypto import get_fernet


def test_running_with_test_settings():
    assert os.environ["DJANGO_SETTINGS_MODULE"] == "config.settings.test"
    assert settings.DEBUG is False


def test_test_database_is_named_after_the_checkout():
    name = settings.DATABASES["default"]["TEST"]["NAME"]
    checkout = re.sub(r"[^a-z0-9]+", "_", settings.REPO_ROOT.name.lower()).strip("_") or "main"

    assert re.fullmatch(r"test_pw_[a-z0-9_]+", name)
    assert len(name) <= 63  # PostgreSQL identifier limit
    assert name == f"test_pw_{checkout}"[:63]


@pytest.mark.django_db
def test_tests_use_the_test_database():
    assert connection.settings_dict["NAME"] == settings.DATABASES["default"]["TEST"]["NAME"]


def test_locale_and_user_model():
    assert settings.TIME_ZONE == "Asia/Kolkata"
    assert settings.USE_TZ is True
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert get_user_model()._meta.label == "accounts.User"
    assert settings.DEFAULT_PHONE_REGION == "IN"


def test_fake_graph_client_is_configured():
    assert settings.WHATSAPP_GRAPH_CLIENT == "apps.whatsapp.client.fake.FakeGraphClient"
    assert isinstance(get_client("test-token"), FakeGraphClient)


def test_tests_never_reach_external_services():
    assert settings.CELERY_TASK_ALWAYS_EAGER is True
    assert settings.CELERY_BROKER_URL == "memory://"
    assert settings.CACHES["default"]["BACKEND"].endswith("LocMemCache")
    assert settings.CHANNEL_LAYERS["default"]["BACKEND"] == "channels.layers.InMemoryChannelLayer"
    assert settings.EMAIL_BACKEND == "django.core.mail.backends.locmem.EmailBackend"
    assert settings.SENTRY_DSN == ""


def test_token_encryption_keys_are_usable():
    assert settings.TOKEN_ENCRYPTION_KEYS
    assert get_fernet() is not None


def test_api_error_handler_is_installed():
    assert settings.REST_FRAMEWORK["EXCEPTION_HANDLER"] == "common.exceptions.api_exception_handler"
    assert settings.REST_FRAMEWORK["DEFAULT_SCHEMA_CLASS"] == "common.schema.AutoSchema"
