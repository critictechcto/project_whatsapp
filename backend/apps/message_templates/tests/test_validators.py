import pytest
from rest_framework.exceptions import ValidationError

from apps.message_templates.validators import (
    validate_components,
    validate_template,
    variable_count,
)

from .conftest import flatten

BODY = {
    "type": "BODY",
    "text": "Hi {{1}}, your order {{2}} has shipped.",
    "example": {"body_text": [["Asha", "A-102"]]},
}

FULL_COMPONENTS = [
    {
        "type": "HEADER",
        "format": "TEXT",
        "text": "Order {{1}}",
        "example": {"header_text": ["A-102"]},
    },
    BODY,
    {"type": "FOOTER", "text": "Reply STOP to opt out"},
    {
        "type": "BUTTONS",
        "buttons": [
            {"type": "QUICK_REPLY", "text": "Thanks"},
            {"type": "QUICK_REPLY", "text": "Need help"},
            {
                "type": "URL",
                "text": "Track order",
                "url": "https://shop.example.in/track/{{1}}",
                "example": ["https://shop.example.in/track/A-102"],
            },
            {"type": "URL", "text": "Visit shop", "url": "https://shop.example.in"},
            {"type": "PHONE_NUMBER", "text": "Call us", "phone_number": "+919800041207"},
            {"type": "COPY_CODE", "example": "SAVE20"},
        ],
    },
]

AUTH_COMPONENTS = [
    {"type": "BODY", "add_security_recommendation": True},
    {"type": "FOOTER", "code_expiration_minutes": 10},
    {"type": "BUTTONS", "buttons": [{"type": "OTP", "otp_type": "COPY_CODE", "text": "Copy code"}]},
]


def errors(components, category="UTILITY") -> list[str]:
    with pytest.raises(ValidationError) as exc_info:
        validate_components(components, category=category)
    return flatten(exc_info.value.detail)


def body(text, samples=None) -> dict:
    component = {"type": "BODY", "text": text}
    if samples is not None:
        component["example"] = {"body_text": [samples]}
    return component


def buttons(*items) -> dict:
    return {"type": "BUTTONS", "buttons": list(items)}


def test_full_standard_template_is_valid():
    validate_template(
        name="order_update_2", language="en_US", category="MARKETING", components=FULL_COMPONENTS
    )


def test_media_and_location_headers_are_valid():
    for header_format in ("IMAGE", "VIDEO", "DOCUMENT", "LOCATION"):
        validate_components([{"type": "HEADER", "format": header_format}, BODY], category="UTILITY")


def test_body_without_variables_needs_no_example():
    validate_components([body("Your order has shipped.")], category="UTILITY")


def test_authentication_template_is_valid():
    validate_components(AUTH_COMPONENTS, category="AUTHENTICATION")


def test_variable_count_counts_distinct_positional_variables():
    assert variable_count("Hi {{1}}, {{2}} and {{1}} again") == 2
    assert variable_count("No variables") == 0
    assert variable_count(None) == 0


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("name", "Order-Update", "lowercase letters, digits and underscores"),
        ("name", "", "Name is required"),
        ("name", "a" * 513, "at most 512"),
        ("language", "english", "Meta language code"),
        ("language", "en-US", "Meta language code"),
        ("category", "PROMOTIONAL", "Category must be one of"),
    ],
)
def test_template_fields_are_checked(field, value, message):
    template = {
        "name": "order_update",
        "language": "en",
        "category": "UTILITY",
        "components": [BODY],
        field: value,
    }
    with pytest.raises(ValidationError) as exc_info:
        validate_template(**template)

    assert field in exc_info.value.detail
    assert any(message in text for text in flatten(exc_info.value.detail[field]))


@pytest.mark.parametrize(
    ("components", "message"),
    [
        ([], "non-empty list"),
        ("BODY", "non-empty list"),
        ([{"type": "FOOTER", "text": "Bye"}], "exactly one BODY"),
        ([BODY, BODY], "Only one BODY"),
        ([{"type": "CAROUSEL"}, BODY], "not supported"),
        ([{"text": "no type"}, BODY], "must be an object with a type"),
        ([body("a" * 1025)], "at most 1024"),
        ([body("")], "BODY: text is required"),
        ([body("Hi {{first_name}}, welcome", ["Asha"])], "named variables"),
        ([body("Hi {{ 1 }}, welcome", ["Asha"])], "not a valid variable"),
        ([body("Hi {{1}} and {{3}} there", ["a", "b"])], "sequentially"),
        ([body("Hi {{2}} there", ["a"])], "sequentially"),
        ([body("{{1}} is your order", ["a"])], "cannot start or end"),
        ([body("Your order is {{1}}", ["a"])], "cannot start or end"),
        ([body("Hi {{1}} and {{2}} there", ["a"])], "need 2 example"),
        ([body("Hi {{1}} there")], "provide 1 example"),
        ([body("Hi there", ["unused"])], "text has no variables"),
        (
            [{"type": "HEADER", "format": "TEXT", "text": "x" * 61}, BODY],
            "at most 60",
        ),
        (
            [
                {
                    "type": "HEADER",
                    "format": "TEXT",
                    "text": "{{1}} and {{2}}",
                    "example": {"header_text": ["a", "b"]},
                },
                BODY,
            ],
            "at most one variable",
        ),
        (
            [{"type": "HEADER", "format": "TEXT", "text": "Order {{1}}"}, BODY],
            "provide 1 example",
        ),
        ([{"type": "HEADER", "format": "GIF"}, BODY], "format must be one of"),
        (
            [{"type": "HEADER", "format": "IMAGE", "text": "Hello"}, BODY],
            "cannot have text",
        ),
        ([BODY, {"type": "FOOTER", "text": "x" * 61}], "at most 60"),
        ([BODY, {"type": "FOOTER", "text": "Code {{1}}"}], "cannot contain variables"),
        ([BODY, buttons()], "at least one button"),
        (
            [BODY, buttons(*[{"type": "QUICK_REPLY", "text": f"Option {n}"} for n in range(11)])],
            "at most 10 buttons",
        ),
        ([BODY, buttons({"type": "QUICK_REPLY", "text": "x" * 26})], "at most 25"),
        ([BODY, buttons({"type": "QUICK_REPLY"})], "text is required"),
        (
            [BODY, buttons(*[{"type": "URL", "text": "Go", "url": "https://x.in"}] * 3)],
            "at most 2 URL",
        ),
        (
            [BODY, buttons({"type": "URL", "text": "Go", "url": "ftp://x.in"})],
            "must start with http",
        ),
        (
            [
                BODY,
                buttons(
                    {
                        "type": "URL",
                        "text": "Go",
                        "url": "https://x.in/{{1}}/track",
                        "example": ["https://x.in/a/track"],
                    }
                ),
            ],
            "must be at the end",
        ),
        (
            [BODY, buttons({"type": "URL", "text": "Go", "url": "https://x.in/{{1}}"})],
            "provide 1 example",
        ),
        (
            [
                BODY,
                buttons(
                    *[{"type": "PHONE_NUMBER", "text": "Call", "phone_number": "+919800041207"}] * 2
                ),
            ],
            "at most 1 PHONE_NUMBER",
        ),
        (
            [BODY, buttons({"type": "PHONE_NUMBER", "text": "Call", "phone_number": "call me"})],
            "phone_number must be",
        ),
        (
            [BODY, buttons(*[{"type": "COPY_CODE", "example": "SAVE20"}] * 2)],
            "at most 1 COPY_CODE",
        ),
        ([BODY, buttons({"type": "COPY_CODE"})], "sample offer code"),
        (
            [BODY, buttons({"type": "OTP", "otp_type": "COPY_CODE"})],
            "only allowed in AUTHENTICATION",
        ),
        ([BODY, buttons({"type": "FLOW", "text": "Book"})], "not supported yet"),
        (
            [
                BODY,
                buttons(
                    {"type": "QUICK_REPLY", "text": "Yes"},
                    {"type": "URL", "text": "Go", "url": "https://x.in"},
                    {"type": "QUICK_REPLY", "text": "No"},
                ),
            ],
            "keep QUICK_REPLY buttons together",
        ),
    ],
)
def test_invalid_standard_components(components, message):
    messages = errors(components)

    assert any(message in text for text in messages), messages


@pytest.mark.parametrize(
    ("components", "message"),
    [
        (
            [{"type": "HEADER", "format": "TEXT", "text": "Code"}, *AUTH_COMPONENTS],
            "cannot have a HEADER",
        ),
        (AUTH_COMPONENTS[:2], "exactly one OTP button"),
        (
            [AUTH_COMPONENTS[0], buttons({"type": "QUICK_REPLY", "text": "Yes"})],
            "only allow an OTP button",
        ),
        (
            [AUTH_COMPONENTS[0], buttons({"type": "OTP", "otp_type": "MAGIC"})],
            "otp_type must be one of",
        ),
        (
            [AUTH_COMPONENTS[0], buttons({"type": "OTP", "otp_type": "ONE_TAP"})],
            "need supported_apps",
        ),
        (
            [
                AUTH_COMPONENTS[0],
                {"type": "FOOTER", "code_expiration_minutes": 100},
                AUTH_COMPONENTS[2],
            ],
            "code_expiration_minutes",
        ),
        (
            [{"type": "BODY", "add_security_recommendation": "yes"}, AUTH_COMPONENTS[2]],
            "add_security_recommendation",
        ),
        (AUTH_COMPONENTS[2:], "exactly one BODY"),
    ],
)
def test_invalid_authentication_components(components, message):
    messages = errors(components, category="AUTHENTICATION")

    assert any(message in text for text in messages), messages


def test_one_tap_with_supported_apps_is_valid():
    validate_components(
        [
            AUTH_COMPONENTS[0],
            buttons(
                {
                    "type": "OTP",
                    "otp_type": "ONE_TAP",
                    "supported_apps": [{"package_name": "in.example", "signature_hash": "abc"}],
                }
            ),
        ],
        category="AUTHENTICATION",
    )


def test_all_errors_are_reported_together():
    messages = errors([body("x" * 1025), {"type": "FOOTER", "text": "Code {{1}}"}])

    assert any("at most 1024" in text for text in messages)
    assert any("cannot contain variables" in text for text in messages)
