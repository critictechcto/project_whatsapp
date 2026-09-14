import dataclasses
import logging
import uuid

import pytest
from django.dispatch import Signal

from common import events
from common.events import AccountUpdate, MessageStatus, MetaError, emit


def make_event() -> AccountUpdate:
    return AccountUpdate(workspace_id=uuid.uuid4(), waba_id="102290129340398", event="X")


def event_log_records(caplog):
    return [record for record in caplog.records if record.name == "common.events"]


def test_emit_calls_every_receiver_and_isolates_failures(caplog):
    signal = Signal()
    calls = []
    error = RuntimeError("boom")

    def first(sender, event, **kwargs):
        calls.append(("first", sender, event))

    def broken(sender, event, **kwargs):
        raise error

    def last(sender, event, **kwargs):
        calls.append(("last", sender, event))

    for receiver in (first, broken, last):
        signal.connect(receiver, weak=False)
    event = make_event()

    with caplog.at_level(logging.ERROR, logger="common.events"):
        failures = emit(signal, event)

    assert calls == [("first", AccountUpdate, event), ("last", AccountUpdate, event)]
    assert failures == [(broken, error)]
    [record] = event_log_records(caplog)
    assert record.levelno == logging.ERROR
    assert "AccountUpdate" in record.getMessage()
    assert "broken" in record.getMessage()
    assert record.exc_info[1] is error


def test_emit_returns_every_failure(caplog):
    signal = Signal()
    errors = [ValueError("one"), KeyError("two")]

    def fail_one(sender, event, **kwargs):
        raise errors[0]

    def fail_two(sender, event, **kwargs):
        raise errors[1]

    signal.connect(fail_one, weak=False)
    signal.connect(fail_two, weak=False)

    with caplog.at_level(logging.ERROR, logger="common.events"):
        failures = emit(signal, make_event())

    assert failures == [(fail_one, errors[0]), (fail_two, errors[1])]
    assert len(event_log_records(caplog)) == 2


def test_emit_without_failures(caplog):
    signal = Signal()
    received = []
    signal.connect(lambda sender, event, **kwargs: received.append(event), weak=False)
    event = make_event()

    with caplog.at_level(logging.ERROR, logger="common.events"):
        assert emit(signal, event) == []

    assert received == [event]
    assert event_log_records(caplog) == []


def test_emit_without_receivers():
    assert emit(Signal(), make_event()) == []


@pytest.mark.parametrize(
    "name",
    [
        "inbound_message_received",
        "message_status_updated",
        "template_status_updated",
        "template_category_updated",
        "template_quality_updated",
        "phone_number_quality_updated",
        "account_updated",
    ],
)
def test_domain_signals_exist(name):
    assert isinstance(getattr(events, name), Signal)


def test_events_are_immutable():
    event = make_event()

    with pytest.raises(dataclasses.FrozenInstanceError):
        event.event = "changed"


def test_message_status_error_codes():
    status = MessageStatus(
        workspace_id=uuid.uuid4(),
        waba_id="1",
        phone_number_id="2",
        wamid="wamid.X",
        recipient_wa_id="919876543210",
        status="failed",
        timestamp=None,
        errors=(MetaError(code=131026), MetaError(code=131047), MetaError(code=131026)),
    )

    assert status.error_codes == frozenset({131026, 131047})
