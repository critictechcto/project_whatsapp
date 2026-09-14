"""GSTIN and state code validation."""

import pytest
from django.core.exceptions import ValidationError

from apps.billing import gst


def with_check_character(first_14: str) -> str:
    return first_14 + gst.gstin_check_character(first_14)


@pytest.mark.parametrize("gstin", ["27AAPFU0939F1ZV", "29AAGCB7383J1Z4", "27AAACR5055K1Z7"])
def test_valid_gstins_pass(gstin):
    assert gst.is_valid_gstin(gstin)
    gst.validate_gstin(gstin)


def test_check_character():
    assert gst.gstin_check_character("27AAPFU0939F1Z") == "V"


@pytest.mark.parametrize(
    ("gstin", "message"),
    [
        ("27AAPFU0939F1ZW", "check character"),
        ("29ABCDE1234F1Z5", "check character"),
        ("27AAPFU0939F1Z", "15-character"),
        ("27aapfu0939f1zv", "15-character"),
        ("27AAPFU0939F0ZV", "15-character"),  # entity number can't be 0
        ("27AAPFU0939F1YV", "15-character"),  # 14th character must be Z
        (with_check_character("40AAPFU0939F1Z"), "unknown state code"),
    ],
)
def test_invalid_gstins_fail(gstin, message):
    assert any(message in error for error in gst.gstin_errors(gstin))
    assert not gst.is_valid_gstin(gstin)
    with pytest.raises(ValidationError):
        gst.validate_gstin(gstin)


def test_blank_gstin_is_allowed():
    gst.validate_gstin("")


@pytest.mark.parametrize("code", ["01", "27", "29", "38", "97"])
def test_valid_state_codes(code):
    gst.validate_state_code(code)


@pytest.mark.parametrize("code", ["00", "39", "99", "7", "MH"])
def test_invalid_state_codes(code):
    with pytest.raises(ValidationError):
        gst.validate_state_code(code)


@pytest.mark.parametrize("value", ["27AAPFU0939F1", "27aapfu0939f1z"])
def test_check_character_needs_14_upper_case_characters(value):
    with pytest.raises(ValueError):
        gst.gstin_check_character(value)
