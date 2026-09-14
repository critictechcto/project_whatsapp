"""Structural checks for templates before they reach Meta.

These catch the common mistakes locally, with clear messages; Meta's review stays the authority.
Scope and simplifications:

- Only positional variables (``{{1}}``, ``{{2}}``) are supported. Named variables
  (``{{first_name}}``) are rejected for now.
- Standard templates (MARKETING, UTILITY): exactly one BODY, optional HEADER, FOOTER and BUTTONS,
  with Meta's length and count limits and matching ``example`` values for every variable.
  Media header samples (``example.header_handle``) are not required here because uploading
  them needs Meta's resumable upload API; Meta rejects the submission if one is missing.
- AUTHENTICATION templates use Meta's preset text, so only the structure is checked: no HEADER,
  a BODY (optionally ``add_security_recommendation``), an optional FOOTER with
  ``code_expiration_minutes`` and exactly one OTP button.
- Button types other than QUICK_REPLY, URL, PHONE_NUMBER, COPY_CODE and OTP (flows, catalogs,
  ...) are rejected as not supported yet.
"""

import re
from collections.abc import Mapping
from itertools import pairwise
from typing import Any

from rest_framework.exceptions import ValidationError

NAME_MAX_LENGTH = 512
NAME_RE = re.compile(r"^[a-z0-9_]+$")
# ISO 639 language, optionally with a region: en, hi, fil, en_US, pt_BR.
LANGUAGE_RE = re.compile(r"^[a-z]{2,3}(_[A-Z]{2})?$")

BODY_MAX_LENGTH = 1024
HEADER_TEXT_MAX_LENGTH = 60
FOOTER_MAX_LENGTH = 60
BUTTON_TEXT_MAX_LENGTH = 25
COPY_CODE_MAX_LENGTH = 15
MAX_BUTTONS = 10
MAX_URL_BUTTONS = 2
MAX_PHONE_BUTTONS = 1
MAX_COPY_CODE_BUTTONS = 1
CODE_EXPIRATION_RANGE = (1, 90)

CATEGORIES = ("MARKETING", "UTILITY", "AUTHENTICATION")
COMPONENT_TYPES = ("HEADER", "BODY", "FOOTER", "BUTTONS")
TEXT_HEADER = "TEXT"
MEDIA_HEADER_FORMATS = ("IMAGE", "VIDEO", "DOCUMENT", "LOCATION")
OTP_TYPES = ("COPY_CODE", "ONE_TAP", "ZERO_TAP")

PLACEHOLDER_RE = re.compile(r"\{\{(.*?)\}\}")
_POSITIONAL_RE = re.compile(r"^[1-9][0-9]*$")
_NAMED_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_LEADING_PLACEHOLDER_RE = re.compile(r"^\{\{[^{}]*\}\}")
_TRAILING_PLACEHOLDER_RE = re.compile(r"\{\{[^{}]*\}\}$")


def variable_numbers(text: str | None) -> list[int]:
    """Positional variable numbers in ``text`` in order of appearance; ignores anything else."""
    if not isinstance(text, str):
        return []
    return [
        int(match.group(1))
        for match in PLACEHOLDER_RE.finditer(text)
        if _POSITIONAL_RE.match(match.group(1))
    ]


def variable_count(text: str | None) -> int:
    """Number of distinct positional variables (``{{1}} .. {{n}}``) in ``text``."""
    return len(set(variable_numbers(text)))


def validate_template_name(name: Any) -> None:
    if not isinstance(name, str) or not name:
        raise ValidationError(["Name is required."])
    if len(name) > NAME_MAX_LENGTH:
        raise ValidationError([f"Name must be at most {NAME_MAX_LENGTH} characters."])
    if not NAME_RE.match(name):
        raise ValidationError(
            ["Name may contain only lowercase letters, digits and underscores (e.g. order_update)."]
        )


def validate_language_code(language: Any) -> None:
    if not isinstance(language, str) or not LANGUAGE_RE.match(language):
        raise ValidationError(["Language must be a Meta language code such as en, hi or en_US."])


def validate_category(category: Any) -> None:
    if category not in CATEGORIES:
        raise ValidationError([f"Category must be one of {', '.join(CATEGORIES)}."])


def validate_template(*, name: Any, language: Any, category: Any, components: Any) -> None:
    """Validate a whole template; raises one ValidationError keyed by field."""
    errors: dict[str, list[str]] = {}
    checks = (
        ("name", lambda: validate_template_name(name)),
        ("language", lambda: validate_language_code(language)),
        ("category", lambda: validate_category(category)),
    )
    for field_name, check in checks:
        try:
            check()
        except ValidationError as exc:
            errors[field_name] = [str(message) for message in exc.detail]
    if "category" not in errors:
        try:
            validate_components(components, category=category)
        except ValidationError as exc:
            errors["components"] = [str(message) for message in exc.detail]
    if errors:
        raise ValidationError(errors)


def validate_components(components: Any, *, category: str) -> None:
    """Validate ``components`` (Meta's format) for ``category``; raises a list of messages."""
    errors: list[str] = []
    if not isinstance(components, list) or not components:
        raise ValidationError(["Components must be a non-empty list."])

    by_type: dict[str, Mapping[str, Any]] = {}
    for index, component in enumerate(components):
        if not isinstance(component, Mapping) or not isinstance(component.get("type"), str):
            errors.append(f"Component {index + 1} must be an object with a type.")
            continue
        component_type = component["type"].upper()
        if component_type not in COMPONENT_TYPES:
            errors.append(
                f"Component type {component['type']!r} is not supported; "
                f"use {', '.join(COMPONENT_TYPES)}."
            )
        elif component_type in by_type:
            errors.append(f"Only one {component_type} component is allowed.")
        else:
            by_type[component_type] = component

    if "BODY" not in by_type:
        errors.append("Templates need exactly one BODY component.")

    if category == "AUTHENTICATION":
        _check_authentication(by_type, errors)
    else:
        if "HEADER" in by_type:
            _check_header(by_type["HEADER"], errors)
        if "BODY" in by_type:
            _check_body(by_type["BODY"], errors)
        if "FOOTER" in by_type:
            _check_footer(by_type["FOOTER"], errors)
        if "BUTTONS" in by_type:
            _check_buttons(by_type["BUTTONS"], errors)

    if errors:
        raise ValidationError(errors)


# --- Standard templates ---------------------------------------------------------------------


def _parse_variables(text: str, where: str, errors: list[str]) -> list[int] | None:
    """Positional numbers in ``text``; records an error and returns None on bad placeholders."""
    numbers: list[int] = []
    valid = True
    for match in PLACEHOLDER_RE.finditer(text):
        inner = match.group(1)
        if _POSITIONAL_RE.match(inner):
            numbers.append(int(inner))
        elif _NAMED_RE.match(inner.strip()):
            errors.append(
                f"{where}: named variables like {{{{{inner.strip()}}}}} are not supported yet; "
                "use positional variables such as {{1}}."
            )
            valid = False
        else:
            errors.append(
                f"{where}: {{{{{inner}}}}} is not a valid variable; write variables as {{{{1}}}}, "
                "{{2}}, ... without spaces."
            )
            valid = False
    if not valid:
        return None
    distinct = sorted(set(numbers))
    if distinct != list(range(1, len(distinct) + 1)):
        found = ", ".join(f"{{{{{n}}}}}" for n in distinct)
        errors.append(f"{where}: variables must be numbered sequentially from {{{{1}}}} ({found}).")
        return None
    return numbers


def _text(component: Mapping[str, Any], where: str, max_length: int, errors: list[str]) -> str:
    text = component.get("text")
    if not isinstance(text, str) or not text.strip():
        errors.append(f"{where}: text is required.")
        return ""
    if len(text) > max_length:
        errors.append(f"{where}: text must be at most {max_length} characters (has {len(text)}).")
    return text


def _example_values(component: Mapping[str, Any], key: str) -> Any:
    example = component.get("example")
    return example.get(key) if isinstance(example, Mapping) else None


def _check_samples(values: Any, expected: int, where: str, errors: list[str]) -> None:
    """``values`` must be a list of ``expected`` non-empty strings (or absent when 0)."""
    if expected == 0:
        if values:
            errors.append(f"{where}: example values are given but the text has no variables.")
        return
    if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
        errors.append(
            f"{where}: provide {expected} example value(s), one non-empty string per variable."
        )
        return
    if len(values) != expected:
        errors.append(
            f"{where}: {expected} variable(s) need {expected} example value(s) "
            f"(found {len(values)})."
        )


def _check_header(component: Mapping[str, Any], errors: list[str]) -> None:
    header_format = str(component.get("format", "")).upper()
    if header_format == TEXT_HEADER:
        text = _text(component, "HEADER", HEADER_TEXT_MAX_LENGTH, errors)
        numbers = _parse_variables(text, "HEADER", errors) if text else []
        if numbers is None:
            return
        count = len(set(numbers))
        if count > 1 or len(numbers) > 1:
            errors.append("HEADER: text headers may contain at most one variable, {{1}}.")
            return
        _check_samples(_example_values(component, "header_text"), count, "HEADER", errors)
    elif header_format in MEDIA_HEADER_FORMATS:
        if component.get("text"):
            errors.append(f"HEADER: {header_format} headers cannot have text.")
    else:
        formats = ", ".join((TEXT_HEADER, *MEDIA_HEADER_FORMATS))
        errors.append(f"HEADER: format must be one of {formats}.")


def _check_body(component: Mapping[str, Any], errors: list[str]) -> None:
    text = _text(component, "BODY", BODY_MAX_LENGTH, errors)
    if not text:
        return
    numbers = _parse_variables(text, "BODY", errors)
    if numbers is None:
        return
    stripped = text.strip()
    if _LEADING_PLACEHOLDER_RE.search(stripped) or _TRAILING_PLACEHOLDER_RE.search(stripped):
        errors.append("BODY: text cannot start or end with a variable.")
    samples = _example_values(component, "body_text")
    if isinstance(samples, list) and len(samples) == 1 and isinstance(samples[0], list):
        samples = samples[0]
    elif samples and len(set(numbers)):
        errors.append("BODY: example.body_text must be a list holding one list of sample values.")
        return
    _check_samples(samples, len(set(numbers)), "BODY", errors)


def _check_footer(component: Mapping[str, Any], errors: list[str]) -> None:
    text = _text(component, "FOOTER", FOOTER_MAX_LENGTH, errors)
    if PLACEHOLDER_RE.search(text):
        errors.append("FOOTER: text cannot contain variables.")


def _button_text(button: Mapping[str, Any], where: str, errors: list[str]) -> None:
    text = button.get("text")
    if not isinstance(text, str) or not text.strip():
        errors.append(f"{where}: text is required.")
    elif len(text) > BUTTON_TEXT_MAX_LENGTH:
        errors.append(f"{where}: text must be at most {BUTTON_TEXT_MAX_LENGTH} characters.")


def _check_buttons(component: Mapping[str, Any], errors: list[str]) -> None:
    buttons = component.get("buttons")
    if not isinstance(buttons, list) or not buttons:
        errors.append("BUTTONS: add at least one button.")
        return
    if len(buttons) > MAX_BUTTONS:
        errors.append(f"BUTTONS: at most {MAX_BUTTONS} buttons are allowed.")

    counts = {"URL": 0, "PHONE_NUMBER": 0, "COPY_CODE": 0}
    kinds: list[bool] = []  # True for quick replies, to check grouping
    for index, button in enumerate(buttons):
        where = f"BUTTONS[{index}]"
        if not isinstance(button, Mapping) or not isinstance(button.get("type"), str):
            errors.append(f"{where}: must be an object with a type.")
            continue
        button_type = button["type"].upper()
        kinds.append(button_type == "QUICK_REPLY")
        if button_type in counts:
            counts[button_type] += 1
        if button_type == "QUICK_REPLY":
            _button_text(button, where, errors)
        elif button_type == "URL":
            _button_text(button, where, errors)
            _check_url_button(button, where, errors)
        elif button_type == "PHONE_NUMBER":
            _button_text(button, where, errors)
            phone = button.get("phone_number")
            if not isinstance(phone, str) or not re.fullmatch(r"\+?[0-9]{6,20}", phone):
                errors.append(f"{where}: phone_number must be a number such as +919800041207.")
        elif button_type == "COPY_CODE":
            example = button.get("example")
            if not isinstance(example, str) or not example.strip():
                errors.append(f"{where}: example (a sample offer code) is required.")
            elif len(example) > COPY_CODE_MAX_LENGTH:
                errors.append(
                    f"{where}: offer code example must be at most {COPY_CODE_MAX_LENGTH} "
                    "characters."
                )
        elif button_type == "OTP":
            errors.append(f"{where}: OTP buttons are only allowed in AUTHENTICATION templates.")
        else:
            errors.append(f"{where}: button type {button['type']!r} is not supported yet.")

    limits = {"URL": MAX_URL_BUTTONS, "PHONE_NUMBER": MAX_PHONE_BUTTONS}
    limits["COPY_CODE"] = MAX_COPY_CODE_BUTTONS
    for button_type, limit in limits.items():
        if counts[button_type] > limit:
            errors.append(f"BUTTONS: at most {limit} {button_type} button(s) are allowed.")
    group_changes = sum(1 for a, b in pairwise(kinds) if a != b)
    if group_changes > 1:
        errors.append("BUTTONS: keep QUICK_REPLY buttons together, before or after the others.")


def _check_url_button(button: Mapping[str, Any], where: str, errors: list[str]) -> None:
    url = button.get("url")
    if not isinstance(url, str) or not re.match(r"^https?://\S+$", url):
        errors.append(f"{where}: url must start with http:// or https://.")
        return
    numbers = _parse_variables(url, where, errors)
    if numbers is None:
        return
    if len(numbers) > 1:
        errors.append(f"{where}: a URL may contain at most one variable, {{{{1}}}}.")
        return
    if numbers and not url.endswith("{{1}}"):
        errors.append(f"{where}: the URL variable must be at the end, e.g. https://x.in/{{{{1}}}}.")
        return
    example = button.get("example")
    if isinstance(example, str):
        example = [example]
    _check_samples(example, len(numbers), where, errors)


# --- Authentication templates ---------------------------------------------------------------


def _check_authentication(by_type: Mapping[str, Mapping[str, Any]], errors: list[str]) -> None:
    if "HEADER" in by_type:
        errors.append("AUTHENTICATION templates cannot have a HEADER.")

    body = by_type.get("BODY")
    if body is not None:
        flag = body.get("add_security_recommendation")
        if flag is not None and not isinstance(flag, bool):
            errors.append("BODY: add_security_recommendation must be true or false.")

    footer = by_type.get("FOOTER")
    if footer is not None:
        minutes = footer.get("code_expiration_minutes")
        low, high = CODE_EXPIRATION_RANGE
        if minutes is not None and (
            isinstance(minutes, bool) or not isinstance(minutes, int) or not low <= minutes <= high
        ):
            errors.append(f"FOOTER: code_expiration_minutes must be a whole number {low}-{high}.")

    buttons_component = by_type.get("BUTTONS")
    buttons = buttons_component.get("buttons") if buttons_component else None
    if not isinstance(buttons, list) or len(buttons) != 1:
        errors.append("AUTHENTICATION templates need exactly one OTP button.")
        return
    button = buttons[0]
    if not isinstance(button, Mapping) or str(button.get("type", "")).upper() != "OTP":
        errors.append("BUTTONS[0]: AUTHENTICATION templates only allow an OTP button.")
        return
    otp_type = str(button.get("otp_type", "")).upper()
    if otp_type not in OTP_TYPES:
        errors.append(f"BUTTONS[0]: otp_type must be one of {', '.join(OTP_TYPES)}.")
    elif otp_type != "COPY_CODE" and not (
        button.get("supported_apps")
        or (button.get("package_name") and button.get("signature_hash"))
    ):
        errors.append(
            f"BUTTONS[0]: {otp_type} buttons need supported_apps (package_name and signature_hash)."
        )
    text = button.get("text")
    if text is not None and (not isinstance(text, str) or len(text) > BUTTON_TEXT_MAX_LENGTH):
        errors.append(f"BUTTONS[0]: text must be at most {BUTTON_TEXT_MAX_LENGTH} characters.")
