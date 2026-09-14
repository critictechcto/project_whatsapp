import pytest
from django.core.exceptions import FieldError
from django.db import IntegrityError, connection

from apps.whatsapp.factories import PhoneNumberFactory, WhatsAppBusinessAccountFactory
from apps.whatsapp.models import WhatsAppBusinessAccount
from common.crypto import decrypt

pytestmark = pytest.mark.django_db


def test_access_token_is_encrypted_at_rest():
    waba = WhatsAppBusinessAccountFactory(access_token="EAAG-secret-token")

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT access_token FROM whatsapp_whatsappbusinessaccount WHERE id = %s", [waba.pk]
        )
        stored = cursor.fetchone()[0]

    assert stored != "EAAG-secret-token"
    assert decrypt(stored) == "EAAG-secret-token"
    assert WhatsAppBusinessAccount.objects.get(pk=waba.pk).access_token == "EAAG-secret-token"


def test_encrypted_field_cannot_be_filtered():
    with pytest.raises(FieldError):
        list(WhatsAppBusinessAccount.objects.filter(access_token="x"))
    assert WhatsAppBusinessAccount.objects.filter(access_token__isnull=True).count() == 0


def test_phone_inherits_waba_workspace():
    phone = PhoneNumberFactory()

    assert phone.workspace_id == phone.waba.workspace_id


def test_only_one_default_phone_per_workspace():
    first = PhoneNumberFactory(is_default=True)

    with pytest.raises(IntegrityError):
        PhoneNumberFactory(waba=first.waba, is_default=True)
