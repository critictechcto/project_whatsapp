import pytest
from cryptography.fernet import Fernet, InvalidToken
from django.core.exceptions import ImproperlyConfigured
from django.core.signals import setting_changed

from common.crypto import DecryptionError, decrypt, encrypt, get_fernet, rotate


def new_key() -> str:
    return Fernet.generate_key().decode()


@pytest.mark.parametrize("value", ["EAAG-secret-token", "123456", "नमस्ते ✓", " padded "])
def test_encrypt_decrypt_round_trip(value):
    token = encrypt(value)

    assert token != value
    assert decrypt(token) == value


def test_ciphertext_is_non_deterministic():
    assert encrypt("same value") != encrypt("same value")


def test_key_rotation(settings):
    old, new = new_key(), new_key()
    settings.TOKEN_ENCRYPTION_KEYS = [old]
    token = encrypt("EAAG-secret")

    settings.TOKEN_ENCRYPTION_KEYS = [new, old]
    assert decrypt(token) == "EAAG-secret"
    rotated = rotate(token)
    assert rotated != token

    settings.TOKEN_ENCRYPTION_KEYS = [new]
    assert decrypt(rotated) == "EAAG-secret"
    with pytest.raises(DecryptionError):
        decrypt(token)


def test_first_key_encrypts(settings):
    primary, secondary = new_key(), new_key()
    settings.TOKEN_ENCRYPTION_KEYS = [primary, secondary]
    token = encrypt("value")

    settings.TOKEN_ENCRYPTION_KEYS = [primary]
    assert decrypt(token) == "value"


def test_keys_accept_comma_separated_string(settings):
    first, second = new_key(), new_key()
    settings.TOKEN_ENCRYPTION_KEYS = f" {first} , {second} ,"
    token = encrypt("value")

    settings.TOKEN_ENCRYPTION_KEYS = [first]
    assert decrypt(token) == "value"


@pytest.mark.parametrize("keys", [[], [""], ["   "], "", " , "])
def test_empty_keys_are_improperly_configured(settings, keys):
    settings.TOKEN_ENCRYPTION_KEYS = keys

    with pytest.raises(ImproperlyConfigured, match="empty"):
        encrypt("value")


@pytest.mark.parametrize("keys", [["not-a-fernet-key"], [new_key(), "short"], ["YWJj"]])
def test_invalid_keys_are_improperly_configured(settings, keys):
    settings.TOKEN_ENCRYPTION_KEYS = keys

    with pytest.raises(ImproperlyConfigured, match="invalid Fernet key"):
        decrypt("anything")


@pytest.mark.parametrize("token", ["garbage", "", "gAAAAABnot-really-a-token"])
def test_garbage_token_raises_decryption_error(token):
    with pytest.raises(DecryptionError) as excinfo:
        decrypt(token)

    assert isinstance(excinfo.value.__cause__, InvalidToken)
    if token:
        assert token not in str(excinfo.value)


def test_token_from_unknown_key_raises_decryption_error():
    foreign = Fernet(new_key()).encrypt(b"secret").decode()

    with pytest.raises(DecryptionError):
        decrypt(foreign)
    with pytest.raises(DecryptionError):
        rotate(foreign)


def test_setting_changed_receiver_clears_cache():
    get_fernet()
    assert get_fernet.cache_info().currsize == 1

    setting_changed.send(sender=None, setting="SOME_OTHER_SETTING", value=None, enter=True)
    assert get_fernet.cache_info().currsize == 1

    setting_changed.send(sender=None, setting="TOKEN_ENCRYPTION_KEYS", value=None, enter=True)
    assert get_fernet.cache_info().currsize == 0
