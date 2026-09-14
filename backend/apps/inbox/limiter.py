"""Per-phone-number send rate limiting for ``inbox.dispatch_message``.

A limiter's ``acquire(key)`` returns 0 when a message may be sent now, otherwise the seconds to
wait before trying again. The implementation is pluggable:

- ``settings.INBOX_SEND_LIMITER`` (dotted path to a zero-argument class) wins when set.
- Otherwise a Redis token bucket is used when the default cache is Redis (dev/prod).
- Otherwise (tests, local memory cache) every send is allowed.

The Redis limiter fails open: if Redis is unreachable, sends are allowed and a warning is logged,
because Meta enforces its own throughput limits anyway.
"""

import functools
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)

KEY_PREFIX = "inbox:send-bucket:"
# Meta's default Cloud API throughput is 80 messages per second per business number.
DEFAULT_RATE_PER_SECOND = 80.0

# Tokens refill continuously at ``rate`` per second up to ``burst``. Returns the wait in seconds as
# a string (Redis truncates Lua numbers to integers). A denied call consumes nothing.
_BUCKET_SCRIPT = """
local rate = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local state = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(state[1])
local ts = tonumber(state[2])
if tokens == nil or ts == nil then
  tokens = burst
  ts = now
end
if now > ts then
  tokens = math.min(burst, tokens + (now - ts) * rate)
  ts = now
end
local wait = 0
if tokens >= 1 then
  tokens = tokens - 1
else
  wait = (1 - tokens) / rate
end
redis.call('HSET', KEYS[1], 'tokens', tostring(tokens), 'ts', tostring(ts))
redis.call('EXPIRE', KEYS[1], math.ceil(burst / rate) + 60)
return tostring(wait)
"""


class SendLimiter(Protocol):
    def acquire(self, key: str) -> float:
        """0 when a send for ``key`` may happen now, else seconds to wait."""
        ...


class AllowAllLimiter:
    def acquire(self, key: str) -> float:
        return 0.0


class RedisTokenBucketLimiter:
    def __init__(
        self,
        url: str | None = None,
        *,
        rate_per_second: float | None = None,
        burst: float | None = None,
    ) -> None:
        self.url = url or getattr(settings, "REDIS_URL", "")
        self.rate = float(
            rate_per_second
            or getattr(settings, "INBOX_SEND_RATE_PER_SECOND", DEFAULT_RATE_PER_SECOND)
        )
        self.burst = float(burst or getattr(settings, "INBOX_SEND_BURST", self.rate))
        self._script = None

    def _get_script(self):
        if self._script is None:
            import redis

            client = redis.Redis.from_url(self.url, socket_timeout=1, socket_connect_timeout=1)
            self._script = client.register_script(_BUCKET_SCRIPT)
        return self._script

    def acquire(self, key: str) -> float:
        try:
            result = self._get_script()(
                keys=[f"{KEY_PREFIX}{key}"], args=[self.rate, self.burst, time.time()]
            )
            return max(0.0, float(result))
        except Exception as exc:  # redis.RedisError, OSError, bad URL: fail open
            logger.warning("Send limiter unavailable, allowing send: %s", type(exc).__name__)
            return 0.0


_override: SendLimiter | None = None


@functools.cache
def _build(path: str | None) -> SendLimiter:
    if path:
        return import_string(path)()
    backend = str(settings.CACHES.get("default", {}).get("BACKEND", ""))
    if backend.endswith("RedisCache") and getattr(settings, "REDIS_URL", ""):
        return RedisTokenBucketLimiter()
    return AllowAllLimiter()


def get_limiter() -> SendLimiter:
    if _override is not None:
        return _override
    return _build(getattr(settings, "INBOX_SEND_LIMITER", None))


@contextmanager
def override_limiter(limiter: SendLimiter) -> Iterator[SendLimiter]:
    """Use ``limiter`` for every ``get_limiter()`` call inside the block (tests)."""
    global _override
    previous = _override
    _override = limiter
    try:
        yield limiter
    finally:
        _override = previous
