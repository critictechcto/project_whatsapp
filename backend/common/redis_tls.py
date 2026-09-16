"""TLS options for Redis clients built from ``REDIS_URL``-style URLs.

Managed Redis/Valkey only accepts TLS (``rediss://``). redis-py verifies certificates by default,
but kombu (the Celery broker) silently falls back to ``CERT_NONE`` unless ``broker_use_ssl`` is
set, so settings build every client's options from here to get the same verified TLS everywhere.

Import-light on purpose: ``config.settings`` imports it before Django is configured.
"""

import ssl
from urllib.parse import urlsplit

CERT_REQS = {
    "required": ssl.CERT_REQUIRED,
    "optional": ssl.CERT_OPTIONAL,
    "none": ssl.CERT_NONE,
}


def is_tls_url(url: str) -> bool:
    return urlsplit(url or "").scheme == "rediss"


def redis_ssl_options(url: str, *, cert_reqs: str = "required", ca_certs: str = "") -> dict:
    """redis-py/kombu keyword arguments for ``url``: empty for ``redis://``, TLS for ``rediss://``.

    ``cert_reqs`` is ``required`` (default), ``optional`` or ``none``; ``ca_certs`` is an optional
    CA bundle path (empty = the system trust store).
    """
    if not is_tls_url(url):
        return {}
    try:
        verify_mode = CERT_REQS[(cert_reqs or "required").strip().lower()]
    except KeyError:
        raise ValueError(
            f"Invalid Redis TLS certificate requirement {cert_reqs!r}; "
            f"use one of {', '.join(CERT_REQS)}."
        ) from None
    options: dict = {"ssl_cert_reqs": verify_mode}
    if ca_certs:
        options["ssl_ca_certs"] = ca_certs
    return options
