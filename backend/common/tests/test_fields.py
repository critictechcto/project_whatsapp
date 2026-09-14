"""EncryptedTextField on its own. Storage in a real table is covered by
``apps/whatsapp/tests/test_models.py``."""

import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import FieldError
from django.db import models
from django.db.models.lookups import IsNull

from common.crypto import DecryptionError, decrypt, encrypt
from common.fields import EncryptedTextField


@pytest.fixture
def field():
    return EncryptedTextField()


def test_is_a_text_field_with_stable_migration_path(field):
    assert isinstance(field, models.TextField)
    _, path, _, _ = field.deconstruct()
    assert path == "common.fields.EncryptedTextField"


def test_prep_value_is_ciphertext(field):
    stored = field.get_prep_value("EAAG-secret-token")

    assert stored != "EAAG-secret-token"
    assert "EAAG" not in stored
    assert decrypt(stored) == "EAAG-secret-token"


def test_prep_value_is_non_deterministic(field):
    assert field.get_prep_value("123456") != field.get_prep_value("123456")


@pytest.mark.parametrize("value", [None, ""])
def test_empty_values_are_stored_as_is(field, value):
    assert field.get_prep_value(value) == value
    assert field.from_db_value(value, None, None) == value


def test_from_db_value_decrypts(field):
    assert field.from_db_value(encrypt("pin-123456"), None, None) == "pin-123456"


def test_from_db_value_with_unknown_key_raises(field):
    foreign = Fernet(Fernet.generate_key()).encrypt(b"secret").decode()

    with pytest.raises(DecryptionError):
        field.from_db_value(foreign, None, None)


def test_isnull_lookup_is_allowed(field):
    assert field.get_lookup("isnull") is IsNull


@pytest.mark.parametrize("lookup", ["exact", "iexact", "contains", "startswith", "in", "gt"])
def test_other_lookups_are_rejected(field, lookup):
    with pytest.raises(FieldError, match=f"'{lookup}'"):
        field.get_lookup(lookup)
