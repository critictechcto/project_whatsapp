import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.contacts.factories import ContactFactory
from apps.contacts.models import ConsentEvent, Contact
from common.events import (
    InboundMessage,
    MessageStatus,
    MetaError,
    emit,
    inbound_message_received,
    message_status_updated,
)

pytestmark = pytest.mark.django_db

WA_ID = "919876543210"


def inbound(workspace_id, *, text="hello", wamid=None, timestamp=None, **kwargs):
    return InboundMessage(
        workspace_id=workspace_id,
        waba_id="waba-1",
        phone_number_id="pn-1",
        wamid=wamid or f"wamid.{uuid.uuid4().hex}",
        from_wa_id=kwargs.pop("from_wa_id", WA_ID),
        timestamp=timestamp or timezone.now(),
        type="text",
        text=text,
        **kwargs,
    )


def status(workspace_id, *, codes=(131050,), wamid="wamid.out-1", recipient=WA_ID):
    return MessageStatus(
        workspace_id=workspace_id,
        waba_id="waba-1",
        phone_number_id="pn-1",
        wamid=wamid,
        recipient_wa_id=recipient,
        status="failed",
        timestamp=timezone.now(),
        errors=tuple(MetaError(code=code) for code in codes),
    )


def send(signal, event):
    assert emit(signal, event) == []


def contact_in(workspace):
    return Contact.objects.get(workspace=workspace, phone_e164=f"+{WA_ID}")


def test_inbound_message_creates_contact_and_tracks_last_inbound(workspace):
    now = timezone.now()

    send(inbound_message_received, inbound(workspace.pk, timestamp=now, profile_name="Asha"))
    # An older message delivered late must not move last_inbound_at back.
    send(inbound_message_received, inbound(workspace.pk, timestamp=now - timedelta(hours=1)))

    contact = contact_in(workspace)
    assert contact.wa_id == WA_ID
    assert contact.name == "Asha"
    assert contact.last_inbound_at == now
    assert contact.marketing_opt_in_status == Contact.OptInStatus.UNKNOWN
    assert not ConsentEvent.objects.exists()


def test_profile_name_only_fills_blank_name(workspace):
    ContactFactory(workspace=workspace, phone_e164=f"+{WA_ID}", wa_id=WA_ID, name="Saved name")

    send(inbound_message_received, inbound(workspace.pk, profile_name="Profile name"))

    assert contact_in(workspace).name == "Saved name"


@pytest.mark.parametrize("text", ["STOP", " stop. ", "Unsubscribe", "stop all!", "Stop promotions"])
def test_opt_out_keywords(workspace, text):
    send(inbound_message_received, inbound(workspace.pk, text=text))

    assert contact_in(workspace).marketing_opt_in_status == Contact.OptInStatus.OPTED_OUT


@pytest.mark.parametrize("text", ["please stop", "stop it now", "stopped", "hello"])
def test_non_keyword_text_does_not_change_consent(workspace, text):
    send(inbound_message_received, inbound(workspace.pk, text=text))

    contact = contact_in(workspace)
    assert contact.marketing_opt_in_status == Contact.OptInStatus.UNKNOWN
    assert contact.last_inbound_at is not None
    assert not ConsentEvent.objects.exists()


def test_stop_redelivery_creates_one_opt_out(workspace):
    event = inbound(workspace.pk, text="STOP", wamid="wamid.stop-1")

    send(inbound_message_received, event)
    send(inbound_message_received, event)

    events = ConsentEvent.objects.filter(contact=contact_in(workspace))
    assert events.count() == 1
    stored = events.get()
    assert stored.action == ConsentEvent.Action.OPT_OUT
    assert stored.source == ConsentEvent.Source.WHATSAPP_KEYWORD
    assert stored.wamid == "wamid.stop-1"


def test_start_opts_in_and_late_stop_redelivery_is_ignored(workspace):
    stop = inbound(workspace.pk, text="stop", wamid="wamid.stop-1")
    send(inbound_message_received, stop)
    send(inbound_message_received, inbound(workspace.pk, text="Start", wamid="wamid.start-1"))
    send(inbound_message_received, stop)

    contact = contact_in(workspace)
    assert contact.marketing_opt_in_status == Contact.OptInStatus.OPTED_IN
    assert contact.opt_in_source == ConsentEvent.Source.WHATSAPP_KEYWORD
    actions = ConsentEvent.objects.filter(contact=contact).order_by("created_at")
    assert [e.action for e in actions] == ["opt_out", "opt_in"]


def test_events_for_unknown_workspace_are_ignored(db):
    send(inbound_message_received, inbound(uuid.uuid4(), text="STOP"))
    send(message_status_updated, status(uuid.uuid4()))

    assert not Contact.objects.exists()


def test_invalid_wa_id_is_ignored(workspace):
    send(inbound_message_received, inbound(workspace.pk, from_wa_id="not-a-number"))

    assert not Contact.objects.exists()


def test_meta_marketing_opt_out_status_opts_out_once(workspace):
    contact = ContactFactory(
        workspace=workspace,
        phone_e164=f"+{WA_ID}",
        wa_id=WA_ID,
        marketing_opt_in_status=Contact.OptInStatus.OPTED_IN,
    )
    event = status(workspace.pk, wamid="wamid.campaign-1")

    send(message_status_updated, event)
    send(message_status_updated, event)

    contact.refresh_from_db()
    assert contact.marketing_opt_in_status == Contact.OptInStatus.OPTED_OUT
    stored = ConsentEvent.objects.get(contact=contact)
    assert stored.source == ConsentEvent.Source.META_MARKETING_OPTOUT
    assert stored.wamid == "wamid.campaign-1"


def test_meta_marketing_opt_out_creates_missing_contact(workspace):
    send(message_status_updated, status(workspace.pk))

    assert contact_in(workspace).marketing_opt_in_status == Contact.OptInStatus.OPTED_OUT


def test_other_status_errors_are_ignored(workspace):
    send(message_status_updated, status(workspace.pk, codes=(131026,)))
    send(message_status_updated, status(workspace.pk, codes=()))

    assert not Contact.objects.exists()
