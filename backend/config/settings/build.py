"""Build-time settings: production settings with placeholder secrets, for ``collectstatic``.

    DJANGO_SETTINGS_MODULE=config.settings.build python manage.py collectstatic --noinput

Needs no environment variables and never connects to Postgres or Redis. Static storage is the
same as production (the whitenoise manifest), so the collected files match what prod serves.
The ASGI app refuses to start with these settings (``BUILD_ONLY``); never run workers with them.
"""

import os

_PLACEHOLDERS = {
    "DJANGO_SECRET_KEY": "build-only-not-a-secret",
    # A syntactically valid Fernet key that encrypts nothing: nothing runs at build time.
    "TOKEN_ENCRYPTION_KEYS": "YnVpbGQtb25seS1ub3QtYS1yZWFsLWtleS0wMDAwMDA=",
    "DJANGO_ALLOWED_HOSTS": "localhost",
    "DATABASE_URL": "postgres://build:build@localhost:5432/build",
    "REDIS_URL": "redis://localhost:6379/0",
    "WS_ALLOWED_ORIGINS": "http://localhost",
}
for _name, _value in _PLACEHOLDERS.items():
    if not os.environ.get(_name):
        os.environ[_name] = _value

from .prod import *  # noqa: E402, F403

BUILD_ONLY = True
