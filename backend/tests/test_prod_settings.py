"""Production settings boot with a minimal environment and wire TLS into every Redis client.

Each case imports ``config.settings.prod`` (or ``build``) in a fresh interpreter, because settings
can only be configured once per process. Nothing here connects to Postgres or Redis.
"""

import json
import os
import ssl
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from django.test import override_settings

from common.redis_tls import redis_ssl_options

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Variables the probes set or clear; anything inherited from the shell or .env is overridden.
_MANAGED = (
    "DJANGO_SETTINGS_MODULE",
    "DJANGO_SECRET_KEY",
    "TOKEN_ENCRYPTION_KEYS",
    "DJANGO_ALLOWED_HOSTS",
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "CORS_ALLOWED_ORIGINS",
    "WS_ALLOWED_ORIGINS",
    "FRONTEND_URL",
    "PUBLIC_API_BASE_URL",
    "DATABASE_URL",
    "DATABASE_CONN_MAX_AGE",
    "DATABASE_DISABLE_SERVER_SIDE_CURSORS",
    "REDIS_URL",
    "CELERY_BROKER_URL",
    "REDIS_SSL_CA_CERTS",
    "REDIS_SSL_CERT_REQS",
    "SENTRY_DSN",
)

_PROBE = r"""
import json, ssl
import django
from django.conf import settings

django.setup()

from channels_redis.utils import create_pool
from django.core.cache import caches
from config.celery import app as celery_app

cache_pool = caches["default"]._cache._get_connection_pool(write=True)
channel_pool = create_pool(settings.CHANNEL_LAYERS["default"]["CONFIG"]["hosts"][0])
broker = celery_app.connection_for_write()
broker_ssl = broker.ssl or {}
db = settings.DATABASES["default"]

print(json.dumps({
    "debug": settings.DEBUG,
    "allowed_hosts": settings.ALLOWED_HOSTS,
    "ws_allowed_origins": settings.WS_ALLOWED_ORIGINS,
    "secure_proxy_ssl_header": list(settings.SECURE_PROXY_SSL_HEADER),
    "ssl_redirect": settings.SECURE_SSL_REDIRECT,
    "middleware_first": settings.MIDDLEWARE[0],
    "staticfiles": settings.STORAGES["staticfiles"]["BACKEND"],
    "build_only": getattr(settings, "BUILD_ONLY", False),
    "db_options": db.get("OPTIONS", {}),
    "db_conn_max_age": db["CONN_MAX_AGE"],
    "db_disable_ssc": db["DISABLE_SERVER_SIDE_CURSORS"],
    "cache_connection_class": cache_pool.connection_class.__name__,
    "cache_cert_reqs": int(cache_pool.connection_kwargs.get("ssl_cert_reqs", -1)),
    "channel_connection_class": channel_pool.connection_class.__name__,
    "channel_cert_reqs": int(channel_pool.connection_kwargs.get("ssl_cert_reqs", -1)),
    "broker_transport": broker.transport_cls,
    "broker_cert_reqs": int(broker_ssl.get("ssl_cert_reqs", -1)),
    "broker_ca_certs": broker_ssl.get("ssl_ca_certs"),
    "cert_required": int(ssl.CERT_REQUIRED),
}))
"""


def _env(**overrides: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in _MANAGED}
    # Empty strings shadow any value the repo-root .env would otherwise supply.
    env.update(dict.fromkeys(_MANAGED, ""))
    env.update(
        {
            "DJANGO_SETTINGS_MODULE": "config.settings.prod",
            "DJANGO_SECRET_KEY": "prod-settings-test-" + "x" * 40,
            "TOKEN_ENCRYPTION_KEYS": Fernet.generate_key().decode(),
            "DJANGO_ALLOWED_HOSTS": "api.upchatz.test",
            "WS_ALLOWED_ORIGINS": "https://app.upchatz.test",
            "DATABASE_URL": "postgres://user:pw@db.upchatz.test:25061/upchatz?sslmode=require",
            "DATABASE_CONN_MAX_AGE": "0",
            "DATABASE_DISABLE_SERVER_SIDE_CURSORS": "true",
            "REDIS_URL": "rediss://default:pw@cache.upchatz.test:25061",
            "REDIS_SSL_CERT_REQS": "required",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    env.update(overrides)
    return env


def _run(code: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed interpreter and test-owned code
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _probe(**overrides: str) -> dict:
    result = _run(_PROBE, _env(**overrides))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_prod_settings_load_with_tls_redis_and_pgbouncer_options():
    info = _probe()

    assert info["debug"] is False
    assert info["allowed_hosts"] == ["api.upchatz.test"]
    assert info["ws_allowed_origins"] == ["https://app.upchatz.test"]
    assert info["secure_proxy_ssl_header"] == ["HTTP_X_FORWARDED_PROTO", "https"]
    assert info["ssl_redirect"] is True
    assert info["middleware_first"] == "common.health.HealthCheckMiddleware"
    assert info["staticfiles"] == "whitenoise.storage.CompressedManifestStaticFilesStorage"
    assert info["build_only"] is False

    assert info["db_options"] == {"sslmode": "require"}
    assert info["db_conn_max_age"] == 0
    assert info["db_disable_ssc"] is True

    required = info["cert_required"]
    assert info["cache_connection_class"] == "SSLConnection"
    assert info["cache_cert_reqs"] == required
    assert info["channel_connection_class"] == "SSLConnection"
    assert info["channel_cert_reqs"] == required
    # CELERY_BROKER_URL defaults to REDIS_URL and gets verified TLS without URL query params.
    assert info["broker_transport"] == "rediss"
    assert info["broker_cert_reqs"] == required


def test_separate_broker_url_and_custom_ca_bundle():
    info = _probe(
        CELERY_BROKER_URL="rediss://default:pw@broker.upchatz.test:25061/1",
        REDIS_SSL_CA_CERTS="/etc/ssl/certs/managed-redis-ca.pem",
    )

    assert info["broker_transport"] == "rediss"
    assert info["broker_cert_reqs"] == info["cert_required"]
    assert info["broker_ca_certs"] == "/etc/ssl/certs/managed-redis-ca.pem"


def test_plain_redis_url_has_no_tls_options():
    info = _probe(REDIS_URL="redis://localhost:6379/0", DATABASE_URL="postgres://u:p@h:5432/d")

    assert info["cache_connection_class"] == "Connection"
    assert info["cache_cert_reqs"] == -1
    assert info["channel_connection_class"] == "Connection"
    assert info["broker_transport"] == "redis"
    assert info["broker_cert_reqs"] == -1
    assert info["db_options"] == {}


_REQUIRED = (
    "DJANGO_SECRET_KEY",
    "TOKEN_ENCRYPTION_KEYS",
    "DJANGO_ALLOWED_HOSTS",
    "DATABASE_URL",
    "REDIS_URL",
    "WS_ALLOWED_ORIGINS",
)


@pytest.mark.parametrize("name", _REQUIRED)
def test_missing_required_variable_refuses_to_start(name):
    result = _run("import django; django.setup()", _env(**{name: ""}))

    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert name in result.stderr


def test_build_settings_need_no_environment():
    env = _env(DJANGO_SETTINGS_MODULE="config.settings.build", **dict.fromkeys(_REQUIRED, ""))
    result = _run(
        "import django; django.setup(); from django.conf import settings; "
        "print(settings.BUILD_ONLY, settings.STORAGES['staticfiles']['BACKEND'])",
        env,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == [
        "True",
        "whitenoise.storage.CompressedManifestStaticFilesStorage",
    ]

    asgi = _run("import config.asgi", env)
    assert asgi.returncode != 0
    assert "collectstatic only" in asgi.stderr


def test_redis_ssl_options():
    assert redis_ssl_options("redis://localhost:6379/0") == {}
    assert redis_ssl_options("memory://") == {}
    options = redis_ssl_options("rediss://h:25061", cert_reqs="REQUIRED", ca_certs="/ca.pem")
    assert options == {"ssl_cert_reqs": ssl.CERT_REQUIRED, "ssl_ca_certs": "/ca.pem"}
    with pytest.raises(ValueError, match="certificate requirement"):
        redis_ssl_options("rediss://h:25061", cert_reqs="sometimes")


@pytest.mark.django_db
@override_settings(ALLOWED_HOSTS=["api.upchatz.test"], SECURE_SSL_REDIRECT=True)
@pytest.mark.parametrize("path", ["/healthz/", "/readyz/"])
def test_health_probes_ignore_host_and_https_redirect(client, path):
    response = client.get(path, HTTP_HOST="10.244.0.17:8080")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@override_settings(ALLOWED_HOSTS=["api.upchatz.test"])
def test_other_paths_still_validate_host(client):
    response = client.get("/api/schema/", HTTP_HOST="evil.example")

    assert response.status_code == 400
