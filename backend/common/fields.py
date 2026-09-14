from django.core.exceptions import FieldError
from django.db import models

from common.crypto import decrypt, encrypt


class EncryptedTextField(models.TextField):
    """Text encrypted at rest with Fernet (see common.crypto).

    Ciphertext is non-deterministic, so the column cannot be filtered on — only ``isnull``
    lookups are allowed. Never expose these values through serializers or logs.
    """

    description = "Text encrypted at rest with Fernet"

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        return encrypt(value)

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        return decrypt(value)

    def get_lookup(self, lookup_name):
        if lookup_name != "isnull":
            raise FieldError(f"EncryptedTextField does not support the '{lookup_name}' lookup.")
        return super().get_lookup(lookup_name)
