import pytest

WABA_ID = "104000000000001"
PHONE_ID = "204000000000001"
SIGNUP_CODE = "signup-code-1"


@pytest.fixture
def meta_signup(fake_graph):
    """Seed the fake Graph API with a WABA, one number and an exchangeable signup code.

    Returns the business token the code exchanges for.
    """
    fake_graph.add_waba(WABA_ID, name="Sharma Traders")
    fake_graph.add_phone_number(WABA_ID, PHONE_ID, display_phone_number="+91 98000 41207")
    return fake_graph.add_signup(SIGNUP_CODE, waba_id=WABA_ID)
