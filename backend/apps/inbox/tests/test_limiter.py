import uuid

import pytest

from apps.inbox import limiter


class DenyAll:
    def acquire(self, key: str) -> float:
        return 1.0


@pytest.fixture
def fresh_limiter_cache():
    limiter._build.cache_clear()
    yield
    limiter._build.cache_clear()


def test_tests_allow_every_send():
    assert isinstance(limiter.get_limiter(), limiter.AllowAllLimiter)
    assert limiter.get_limiter().acquire("any") == 0.0


def test_override_limiter():
    deny = DenyAll()

    with limiter.override_limiter(deny):
        assert limiter.get_limiter() is deny

    assert limiter.get_limiter() is not deny


def test_setting_selects_the_limiter(settings, fresh_limiter_cache):
    settings.INBOX_SEND_LIMITER = "apps.inbox.tests.test_limiter.DenyAll"

    assert isinstance(limiter.get_limiter(), DenyAll)


def test_redis_cache_selects_the_token_bucket(settings, fresh_limiter_cache):
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache"}}
    settings.REDIS_URL = "redis://127.0.0.1:1/0"

    assert isinstance(limiter.get_limiter(), limiter.RedisTokenBucketLimiter)


def test_redis_limiter_fails_open():
    unreachable = limiter.RedisTokenBucketLimiter("redis://127.0.0.1:1/0")

    assert unreachable.acquire("106540352242922") == 0.0


def test_redis_token_bucket():
    redis = pytest.importorskip("redis")
    url = "redis://localhost:6379/15"
    try:
        redis.Redis.from_url(url, socket_connect_timeout=0.5).ping()
    except redis.RedisError:
        pytest.skip("Redis is not running")
    bucket = limiter.RedisTokenBucketLimiter(url, rate_per_second=1, burst=2)
    key = f"test-{uuid.uuid4().hex}"
    try:
        assert bucket.acquire(key) == 0.0
        assert bucket.acquire(key) == 0.0
        assert 0.0 < bucket.acquire(key) <= 1.0
    finally:
        redis.Redis.from_url(url).delete(f"{limiter.KEY_PREFIX}{key}")


def test_redis_limiter_uses_verified_tls_for_rediss(monkeypatch, settings):
    import ssl

    import redis

    settings.REDIS_SSL_CERT_REQS = "required"
    settings.REDIS_SSL_CA_CERTS = ""
    captured = {}

    class FakeClient:
        def register_script(self, script):
            return script

    def fake_from_url(url, **kwargs):
        captured.update(kwargs)
        return FakeClient()

    monkeypatch.setattr(redis.Redis, "from_url", staticmethod(fake_from_url))
    limiter.RedisTokenBucketLimiter("rediss://user:pw@example.com:25061/0")._get_script()

    assert captured["ssl_cert_reqs"] == ssl.CERT_REQUIRED
