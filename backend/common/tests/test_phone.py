import pytest

from common.phone import InvalidPhoneNumber, normalize_e164, to_wa_id


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+91 98765 43210", "+919876543210"),
        ("+91-98765-43210", "+919876543210"),
        ("(+91) 98765.43210", "+919876543210"),
        ("09876543210", "+919876543210"),
        ("098765 43210", "+919876543210"),
        ("9876543210", "+919876543210"),
        ("  9876543210  ", "+919876543210"),
        ("919876543210", "+919876543210"),  # a wa_id: country code, no '+'
        (919876543210, "+919876543210"),
        ("+971501234567", "+971501234567"),  # UAE
        ("00971501234567", "+971501234567"),  # UAE with the international dialling prefix
        ("971501234567", "+971501234567"),  # UAE wa_id
    ],
)
def test_normalize_e164(raw, expected):
    assert normalize_e164(raw) == expected


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("98765", "not a valid phone number"),
        ("+91 12345", "not a valid phone number"),
        ("", "required"),
        ("   ", "required"),
        (None, "required"),
        ("abcdef", "not a phone number"),
        ("call me", "not a phone number"),
    ],
)
def test_invalid_numbers_raise(raw, message):
    with pytest.raises(InvalidPhoneNumber, match=message):
        normalize_e164(raw)


def test_invalid_phone_number_is_a_value_error():
    assert issubclass(InvalidPhoneNumber, ValueError)


def test_default_region_argument():
    assert normalize_e164("050 123 4567", default_region="AE") == "+971501234567"


def test_default_region_setting(settings):
    settings.DEFAULT_PHONE_REGION = "AE"

    assert normalize_e164("0501234567") == "+971501234567"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("+919876543210", "919876543210"), ("919876543210", "919876543210")],
)
def test_to_wa_id(value, expected):
    assert to_wa_id(value) == expected


def test_wa_id_round_trip():
    e164 = normalize_e164("+91 98765 43210")

    assert normalize_e164(to_wa_id(e164)) == e164
