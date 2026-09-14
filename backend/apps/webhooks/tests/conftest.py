import pytest

from apps.whatsapp.factories import PhoneNumberFactory

from .helpers import (
    ALL_SIGNALS,
    OTHER_PHONE_NUMBER_ID,
    OTHER_WABA_ID,
    PHONE_NUMBER_ID,
    WABA_ID,
    Recorder,
)


@pytest.fixture
def isolated_signals():
    """Detach other apps' receivers for the test so only receivers connected here run."""
    saved = [(signal, signal.receivers) for signal in ALL_SIGNALS]
    for signal in ALL_SIGNALS:
        signal.receivers = []
        signal.sender_receivers_cache.clear()
    yield
    for signal, receivers in saved:
        signal.receivers = receivers
        signal.sender_receivers_cache.clear()


@pytest.fixture
def recorder(isolated_signals):
    recorder = Recorder()
    for signal in ALL_SIGNALS:
        signal.connect(recorder, weak=False)
    return recorder


@pytest.fixture
def connected_number(workspace):
    """The fixtures' phone number and WABA, connected to ``workspace``."""
    return PhoneNumberFactory(
        workspace=workspace,
        waba__workspace=workspace,
        waba__waba_id=WABA_ID,
        phone_number_id=PHONE_NUMBER_ID,
        display_phone_number="15550783881",
    )


@pytest.fixture
def other_number(other_workspace):
    """A second number/WABA belonging to ``other_workspace``."""
    return PhoneNumberFactory(
        workspace=other_workspace,
        waba__workspace=other_workspace,
        waba__waba_id=OTHER_WABA_ID,
        phone_number_id=OTHER_PHONE_NUMBER_ID,
        display_phone_number="15550001111",
    )
