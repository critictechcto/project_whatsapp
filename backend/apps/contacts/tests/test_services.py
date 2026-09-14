import pytest

from apps.contacts import services
from apps.contacts.factories import ContactFactory
from apps.contacts.models import ConsentEvent, Contact
from common.phone import InvalidPhoneNumber

pytestmark = pytest.mark.django_db


def test_get_or_create_from_wa_is_idempotent(workspace):
    first = services.get_or_create_from_wa(workspace, "919876543210", profile_name="Asha")
    second = services.get_or_create_from_wa(workspace, "919876543210", profile_name="Other")

    assert first.pk == second.pk
    assert (second.phone_e164, second.wa_id, second.name) == (
        "+919876543210",
        "919876543210",
        "Asha",
    )
    assert Contact.objects.count() == 1


def test_get_or_create_from_wa_rejects_garbage(workspace):
    with pytest.raises(InvalidPhoneNumber):
        services.get_or_create_from_wa(workspace, "abc")


def test_record_consent_only_on_state_change(workspace, user):
    contact = ContactFactory(workspace=workspace)

    assert services.record_opt_out(contact, source="manual") is not None
    assert services.record_opt_out(contact, source="manual") is None
    event = services.record_opt_in(contact, source="api", actor=user, evidence="Form")

    assert event is not None and event.actor == user
    assert contact.marketing_opt_in_status == Contact.OptInStatus.OPTED_IN
    assert services.is_marketing_allowed(contact)
    assert ConsentEvent.objects.filter(contact=contact).count() == 2


def test_record_consent_skips_seen_wamid(workspace):
    contact = ContactFactory(workspace=workspace)
    services.record_opt_out(contact, source="whatsapp_keyword", wamid="wamid.1")
    services.record_opt_in(contact, source="whatsapp_keyword", wamid="wamid.2")

    assert services.record_opt_out(contact, source="whatsapp_keyword", wamid="wamid.1") is None
    assert contact.marketing_opt_in_status == Contact.OptInStatus.OPTED_IN


@pytest.mark.parametrize(
    ("status", "allowed"),
    [
        (Contact.OptInStatus.UNKNOWN, False),
        (Contact.OptInStatus.OPTED_IN, True),
        (Contact.OptInStatus.OPTED_OUT, False),
    ],
)
def test_is_marketing_allowed(workspace, status, allowed):
    contact = ContactFactory(workspace=workspace, marketing_opt_in_status=status)

    assert services.is_marketing_allowed(contact) is allowed
    assert Contact.objects.marketing_allowed().filter(pk=contact.pk).exists() is allowed


def test_consent_events_are_append_only(workspace):
    contact = ContactFactory(workspace=workspace)
    event = services.record_opt_out(contact, source="manual")

    event.evidence = "changed"
    with pytest.raises(ValueError, match="append-only"):
        event.save()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("STOP", "opt_out"),
        ("Stop  Promotions!!", "opt_out"),
        ("subscribe.", "opt_in"),
        ("START", "opt_in"),
        ("stop please", None),
        ("", None),
        (None, None),
    ],
)
def test_match_consent_keyword(text, expected):
    assert services.match_consent_keyword(text) == expected
