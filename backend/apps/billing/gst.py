"""GST reference data and GSTIN validation. No database access."""

import re

from django.core.exceptions import ValidationError

# GST state and union territory codes (the first two digits of a GSTIN).
GST_STATE_CODES: dict[str, str] = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "25": "Daman and Diu",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "28": "Andhra Pradesh (old)",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "97": "Other Territory",
}

# 2-digit state code, 10-character PAN, entity number, "Z", check character.
GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_check_character(first_14: str) -> str:
    """The GSTIN check character for the first 14 characters (mod-36 Luhn variant)."""
    if len(first_14) != 14 or any(char not in _ALPHABET for char in first_14):
        raise ValueError("Expected the first 14 characters of a GSTIN.")
    total = 0
    for index, char in enumerate(first_14):
        product = _ALPHABET.index(char) * (2 if index % 2 else 1)
        total += product // 36 + product % 36
    return _ALPHABET[(36 - total % 36) % 36]


def gstin_errors(gstin: str) -> list[str]:
    """Reasons ``gstin`` is invalid; empty when it is a well-formed GSTIN."""
    if not GSTIN_RE.fullmatch(gstin or ""):
        return ["Enter a valid 15-character GSTIN."]
    errors = []
    if gstin[:2] not in GST_STATE_CODES:
        errors.append("The GSTIN starts with an unknown state code.")
    if gstin_check_character(gstin[:14]) != gstin[14]:
        errors.append("The GSTIN check character is wrong; check for typos.")
    return errors


def is_valid_gstin(gstin: str) -> bool:
    return not gstin_errors(gstin)


def validate_gstin(value: str) -> None:
    """Model/form validator. Blank values are allowed (unregistered businesses)."""
    if value:
        errors = gstin_errors(value)
        if errors:
            raise ValidationError(errors, code="invalid_gstin")


def validate_state_code(value: str) -> None:
    if value and value not in GST_STATE_CODES:
        raise ValidationError("Enter a valid 2-digit GST state code.", code="invalid_state_code")
