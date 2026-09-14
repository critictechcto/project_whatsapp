"""Template variables for campaigns: which placeholders a template needs, whether a
``VariableMapping`` fills them, and resolving a mapping for one contact into send parameters.

A mapping is ``{"body": [source], "header": source | None, "buttons": {"<index>": source}}`` where a
source is ``{"source": "contact_field" | "attribute" | "static", "value": str, "fallback": str}``.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from apps.inbox.sending import TemplateContent
from apps.message_templates import validators
from apps.message_templates.models import MessageTemplate

CONTACT_FIELDS = ("name", "phone_e164", "email")
MEDIA_HEADER_FORMATS = ("IMAGE", "VIDEO", "DOCUMENT")

HEADER_TEXT = "text"
HEADER_MEDIA = "media"  # the mapped value is a public media URL
HEADER_UNSUPPORTED = "unsupported"  # LOCATION headers need coordinates, not a single value


@dataclass(frozen=True, slots=True)
class TemplateSlots:
    body: int
    header: str | None = None
    # Button index -> whether a value is required. Buttons that take no parameter are absent.
    buttons: dict[int, bool] = field(default_factory=dict)


def _components(template: MessageTemplate) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for component in template.components or []:
        if isinstance(component, Mapping) and isinstance(component.get("type"), str):
            result.setdefault(component["type"].upper(), component)
    return result


def template_slots(template: MessageTemplate) -> TemplateSlots:
    components = _components(template)
    is_authentication = template.category == MessageTemplate.Category.AUTHENTICATION
    body = components.get("BODY") or {}
    body_count = 1 if is_authentication else validators.variable_count(body.get("text"))

    header_kind = None
    header = components.get("HEADER")
    if header is not None and not is_authentication:
        header_format = str(header.get("format", "")).upper()
        if header_format == validators.TEXT_HEADER:
            header_kind = HEADER_TEXT if validators.variable_count(header.get("text")) else None
        elif header_format in MEDIA_HEADER_FORMATS:
            header_kind = HEADER_MEDIA
        else:
            header_kind = HEADER_UNSUPPORTED

    buttons: dict[int, bool] = {}
    raw_buttons = (components.get("BUTTONS") or {}).get("buttons")
    for index, button in enumerate(raw_buttons if isinstance(raw_buttons, list) else []):
        if not isinstance(button, Mapping):
            continue
        button_type = str(button.get("type", "")).upper()
        url_variable = button_type == "URL" and validators.variable_count(button.get("url"))
        if url_variable or button_type == "COPY_CODE":
            buttons[index] = True
        elif button_type in ("OTP", "QUICK_REPLY"):
            buttons[index] = False
    return TemplateSlots(body=body_count, header=header_kind, buttons=buttons)


def mapping_errors(template: MessageTemplate, mapping: Mapping[str, Any]) -> dict[str, list[str]]:
    """Field errors when ``mapping`` doesn't match the template's placeholders (empty when ok)."""
    slots = template_slots(template)
    errors: dict[str, list[str]] = {}

    body = mapping.get("body") or []
    if len(body) != slots.body:
        errors["body"] = [
            f"The template body has {slots.body} variable(s); map exactly {slots.body} "
            f"(got {len(body)})."
        ]

    header = mapping.get("header")
    if slots.header == HEADER_UNSUPPORTED:
        errors["header"] = ["Templates with a location header can't be used in campaigns yet."]
    elif slots.header is None and header is not None:
        errors["header"] = ["This template's header has no variable."]
    elif slots.header == HEADER_TEXT and header is None:
        errors["header"] = ["Map a value for the header variable."]
    elif slots.header == HEADER_MEDIA and header is None:
        errors["header"] = ["Map a public link to the header image, video or document."]

    buttons = mapping.get("buttons") or {}
    button_errors = []
    for key in buttons:
        if int(key) not in slots.buttons:
            button_errors.append(f"Button {key} takes no variable.")
    for index, required in slots.buttons.items():
        if required and str(index) not in buttons:
            button_errors.append(f"Map a value for button {index}.")
    if button_errors:
        errors["buttons"] = button_errors
    return errors


def resolve_value(source: Mapping[str, Any], contact) -> str:
    """The source's value for ``contact``, else its fallback; whitespace is collapsed because
    Meta rejects parameters with newlines, tabs or long runs of spaces."""
    kind = source.get("source")
    value = source.get("value") or ""
    raw: Any = ""
    if kind == "contact_field" and value in CONTACT_FIELDS:
        raw = getattr(contact, value, "")
    elif kind == "attribute":
        attributes = contact.attributes if isinstance(contact.attributes, Mapping) else {}
        raw = attributes.get(value)
    elif kind == "static":
        raw = value
    text = "" if raw is None or isinstance(raw, Mapping | list) else " ".join(str(raw).split())
    if not text:
        text = " ".join(str(source.get("fallback") or "").split())
    return text


def resolve_params(mapping: Mapping[str, Any], contact) -> dict[str, Any] | None:
    """``{"body", "header", "buttons"}`` for ``contact``, or None when any value is empty."""
    body = []
    for source in mapping.get("body") or []:
        value = resolve_value(source, contact)
        if not value:
            return None
        body.append(value)
    header = None
    if mapping.get("header"):
        header = resolve_value(mapping["header"], contact)
        if not header:
            return None
    buttons = {}
    for key, source in (mapping.get("buttons") or {}).items():
        value = resolve_value(source, contact)
        if not value:
            return None
        buttons[str(key)] = value
    return {"body": body, "header": header, "buttons": buttons}


def template_content(template: MessageTemplate, params: Mapping[str, Any]) -> TemplateContent:
    header: str | dict | None = params.get("header")
    if header is not None and template_slots(template).header == HEADER_MEDIA:
        header = {"link": header}
    buttons = {int(key): value for key, value in (params.get("buttons") or {}).items()}
    return TemplateContent(
        template=template,
        body_params=tuple(params.get("body") or ()),
        header_param=header,
        button_params=buttons or None,
    )
