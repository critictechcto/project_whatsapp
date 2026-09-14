"""Fernet encryption for secrets stored in the database (customer Meta tokens, PINs).

``settings.TOKEN_ENCRYPTION_KEYS`` is a list of Fernet keys. The first key encrypts; every key
can decrypt, so rotate by prepending a new key, re-encrypting rows with :func:`rotate`, then
dropping the old key.
"""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

GENERATE_KEY_HINT = (
    "Generate one with: uv run python -c "
    '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
)


class DecryptionError(Exception):
    """Stored ciphertext could not be decrypted with any configured key."""


@lru_cache(maxsize=1)
def get_fernet() -> MultiFernet:
    keys = settings.TOKEN_ENCRYPTION_KEYS
    if isinstance(keys, str):
        keys = keys.split(",")
    keys = [key.strip() for key in keys if key and key.strip()]
    if not keys:
        raise ImproperlyConfigured(f"TOKEN_ENCRYPTION_KEYS is empty. {GENERATE_KEY_HINT}")
    try:
        return MultiFernet([Fernet(key) for key in keys])
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured(
            f"TOKEN_ENCRYPTION_KEYS contains an invalid Fernet key. {GENERATE_KEY_HINT}"
        ) from exc


def encrypt(value: str) -> str:
    return get_fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return get_fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError("Unable to decrypt value with the configured keys.") from exc


def rotate(token: str) -> str:
    """Re-encrypt ``token`` with the current primary key."""
    try:
        return get_fernet().rotate(token.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError("Unable to decrypt value with the configured keys.") from exc
