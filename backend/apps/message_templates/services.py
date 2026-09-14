"""Template lifecycle: local drafts, submission to Meta, sync, deletion, previews and the
``template`` object used to send a template message (wave 2)."""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from apps.whatsapp.client import get_client
from apps.whatsapp.client.errors import GraphAPIError, InvalidParameterError, TemplateError
from apps.whatsapp.models import WhatsAppBusinessAccount
from common.exceptions import Conflict, UpstreamUnavailable

from . import validators
from .models import MessageTemplate

logger = logging.getLogger(__name__)

Status = MessageTemplate.Status

EDITABLE_FIELDS = ("waba", "name", "language", "category", "components")
# Meta identifies a submitted template by these; changing them needs a new template.
IDENTITY_FIELDS = ("waba", "name", "language")


class TemplateNotEditable(Conflict):
    default_code = "template_not_editable"
    default_detail = "Only draft or rejected templates can be changed."


class TemplateNotSubmittable(Conflict):
    default_code = "template_not_submittable"
    default_detail = "Only draft or rejected templates can be submitted."


class TemplateNotApproved(Conflict):
    default_code = "template_not_approved"
    default_detail = "Only approved templates can be sent."


class MetaRequestFailed(APIException):
    status_code = 400
    default_code = "meta_request_failed"
    default_detail = "Meta rejected the request."


# --- Drafts -----------------------------------------------------------------------------------


def _check_waba(workspace, waba: WhatsAppBusinessAccount) -> None:
    if waba.workspace_id != workspace.pk:
        raise ValidationError(
            {"waba": ["The WhatsApp Business Account belongs to a different workspace."]}
        )


def _check_unique(template: MessageTemplate) -> None:
    clash = MessageTemplate.objects.filter(
        waba_id=template.waba_id, name=template.name, language=template.language
    ).exclude(pk=template.pk)
    if clash.exists():
        raise ValidationError(
            {"name": ["A template with this name and language already exists for this account."]}
        )


def _save(template: MessageTemplate) -> MessageTemplate:
    try:
        template.full_clean(
            exclude=["components"], validate_unique=False, validate_constraints=False
        )
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    _check_unique(template)
    try:
        with transaction.atomic():
            template.save()
    except IntegrityError as exc:
        raise ValidationError(
            {"name": ["A template with this name and language already exists for this account."]}
        ) from exc
    return template


def create_draft(
    *,
    workspace,
    waba: WhatsAppBusinessAccount,
    name: str,
    language: str,
    category: str,
    components: list[dict[str, Any]],
    created_by=None,
) -> MessageTemplate:
    """Validate and store a local DRAFT; nothing is sent to Meta."""
    _check_waba(workspace, waba)
    validators.validate_template(
        name=name, language=language, category=category, components=components
    )
    template = MessageTemplate(
        workspace=workspace,
        waba=waba,
        name=name,
        language=language,
        category=category,
        components=components,
        status=Status.DRAFT,
        created_by=created_by,
    )
    return _save(template)


def update_template(template: MessageTemplate, **changes: Any) -> MessageTemplate:
    """Edit a DRAFT or REJECTED template. Submitted templates keep their waba, name and language."""
    if not template.is_editable:
        raise TemplateNotEditable()
    unknown = set(changes) - set(EDITABLE_FIELDS)
    if unknown:
        raise ValidationError({field: ["This field cannot be changed."] for field in unknown})
    if template.meta_template_id:
        locked = [
            field
            for field in IDENTITY_FIELDS
            if field in changes and changes[field] != getattr(template, field)
        ]
        if locked:
            raise ValidationError(
                {field: ["Cannot be changed after the template was submitted."] for field in locked}
            )
    if "waba" in changes:
        _check_waba(template.workspace, changes["waba"])
    for field, value in changes.items():
        setattr(template, field, value)
    validators.validate_template(
        name=template.name,
        language=template.language,
        category=template.category,
        components=template.components,
    )
    return _save(template)


# --- Meta calls -------------------------------------------------------------------------------


def _raise_for_graph_error(exc: GraphAPIError) -> None:
    message = exc.message or "Meta rejected the request."
    if exc.details:
        message = f"{message} {exc.details}"
    if isinstance(exc, TemplateError | InvalidParameterError):
        raise ValidationError({"meta": [message]}) from exc
    if exc.retryable:
        raise UpstreamUnavailable() from exc
    raise MetaRequestFailed(message) from exc


def submit(template: MessageTemplate) -> MessageTemplate:
    """Send a DRAFT or REJECTED template to Meta for review."""
    with transaction.atomic():
        template = (
            MessageTemplate.objects.select_for_update().select_related("waba").get(pk=template.pk)
        )
        if not template.is_editable:
            raise TemplateNotSubmittable()
        validators.validate_template(
            name=template.name,
            language=template.language,
            category=template.category,
            components=template.components,
        )
        payload = {
            "name": template.name,
            "language": template.language,
            "category": template.category,
            "components": template.components,
        }
        client = get_client(template.waba.access_token)
        try:
            response = client.create_template(template.waba.waba_id, payload)
        except GraphAPIError as exc:
            logger.info("Template %s submission failed: %s", template.pk, exc)
            _raise_for_graph_error(exc)

        template.meta_template_id = str(response["id"])
        template.status = _status(response.get("status"), default=Status.PENDING)
        if response.get("category") in MessageTemplate.Category.values:
            template.category = response["category"]
        template.rejected_reason = ""
        template.submitted_at = timezone.now()
        template.save(
            update_fields=[
                "meta_template_id",
                "status",
                "category",
                "rejected_reason",
                "submitted_at",
                "updated_at",
            ]
        )
    return template


def delete(template: MessageTemplate) -> None:
    """Delete at Meta (when submitted and not already gone), then locally."""
    if template.meta_template_id and template.status != Status.DELETED:
        client = get_client(template.waba.access_token)
        try:
            client.delete_template(
                template.waba.waba_id, name=template.name, template_id=template.meta_template_id
            )
        except GraphAPIError as exc:
            logger.info("Template %s deletion failed: %s", template.pk, exc)
            _raise_for_graph_error(exc)
    template.delete()


@dataclass(frozen=True, slots=True)
class SyncResult:
    created: int = 0
    updated: int = 0
    deleted: int = 0


def _status(value: Any, *, default: str) -> str:
    value = str(value or "").upper()
    return value if value in Status.values else default


def _quality(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("score")
    value = str(value or "").upper()
    values = MessageTemplate.QualityScore.values
    return value if value in values else MessageTemplate.QualityScore.UNKNOWN


def normalize_reason(reason: Any) -> str:
    reason = str(reason or "").strip()
    return "" if reason.upper() == "NONE" else reason[:255]


def sync_waba(waba: WhatsAppBusinessAccount, *, page_size: int = 100) -> SyncResult:
    """Mirror every template Meta holds for ``waba``.

    Upserts by Meta id, falling back to (waba, name, language). Local templates with a Meta id
    that Meta no longer returns are marked DELETED. Graph errors propagate (the task retries).
    """
    client = get_client(waba.access_token)
    now = timezone.now()
    seen: set[str] = set()
    created = updated = 0
    after: str | None = None

    while True:
        page = client.list_templates(waba.waba_id, after=after, limit=page_size)
        for item in page.get("data") or []:
            if not isinstance(item, Mapping) or not item.get("id"):
                continue
            meta_id = str(item["id"])
            if meta_id in seen:
                continue
            seen.add(meta_id)
            was_created = _upsert_from_meta(waba, meta_id, item, now)
            if was_created is None:
                continue
            created += was_created
            updated += not was_created
        paging = page.get("paging") or {}
        after = (paging.get("cursors") or {}).get("after")
        if not paging.get("next") or not after:
            break

    deleted = (
        MessageTemplate.objects.filter(waba=waba)
        .exclude(meta_template_id="")
        .exclude(meta_template_id__in=seen)
        .exclude(status=Status.DELETED)
        .update(status=Status.DELETED, last_synced_at=now, updated_at=now)
    )
    return SyncResult(created=created, updated=updated, deleted=deleted)


def _upsert_from_meta(
    waba: WhatsAppBusinessAccount, meta_id: str, item: Mapping[str, Any], now
) -> bool | None:
    """Create or update one template from Meta's JSON. Returns True if created, None if
    skipped."""
    name = str(item.get("name") or "")
    language = str(item.get("language") or "")
    template = MessageTemplate.objects.filter(waba=waba, meta_template_id=meta_id).first()
    if template is None:
        template = MessageTemplate.objects.filter(waba=waba, name=name, language=language).first()
        if template is not None and template.meta_template_id not in ("", meta_id):
            # Same name/language was recreated at Meta: take over the row.
            logger.info("Template %s now maps to Meta id %s", template.pk, meta_id)
    if template is None and MessageTemplate.objects.filter(meta_template_id=meta_id).exists():
        logger.warning("Meta template %s already belongs to another account; skipped", meta_id)
        return None

    is_new = template is None
    if is_new:
        template = MessageTemplate(workspace_id=waba.workspace_id, waba=waba)
    template.meta_template_id = meta_id
    template.name = name or template.name
    template.language = language or template.language
    template.status = _status(item.get("status"), default=template.status or Status.PENDING)
    if item.get("category"):
        template.category = str(item["category"]).upper()
    if "quality_score" in item:
        template.quality_score = _quality(item.get("quality_score"))
    template.rejected_reason = normalize_reason(item.get("rejected_reason"))
    if isinstance(item.get("components"), list):
        template.components = item["components"]
    template.last_synced_at = now
    template.save()
    return is_new


# --- Rendering and sending --------------------------------------------------------------------


def _components_by_type(template: MessageTemplate) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for component in template.components or []:
        if isinstance(component, Mapping) and isinstance(component.get("type"), str):
            result.setdefault(component["type"].upper(), component)
    return result


def _buttons(components: Mapping[str, Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    buttons = (components.get("BUTTONS") or {}).get("buttons")
    return [b for b in buttons if isinstance(b, Mapping)] if isinstance(buttons, list) else []


def _is_authentication(template: MessageTemplate) -> bool:
    return template.category == MessageTemplate.Category.AUTHENTICATION


def _substitute(text: str, values: Sequence[str], samples: Sequence[str]) -> str:
    def replace(match):
        inner = match.group(1)
        if not inner.isdigit():
            return match.group(0)
        index = int(inner) - 1
        if 0 <= index < len(values):
            return str(values[index])
        if 0 <= index < len(samples):
            return str(samples[index])
        return match.group(0)

    return validators.PLACEHOLDER_RE.sub(replace, text)


def _samples(component: Mapping[str, Any], key: str) -> list[str]:
    example = component.get("example")
    values = example.get(key) if isinstance(example, Mapping) else None
    if key == "body_text" and isinstance(values, list) and values and isinstance(values[0], list):
        values = values[0]
    return [str(v) for v in values] if isinstance(values, list) else []


def _authentication_body(body: Mapping[str, Any]) -> str:
    text = body.get("text")
    if isinstance(text, str) and text:
        return text
    text = "*{{1}}* is your verification code."
    if body.get("add_security_recommendation"):
        text += " For your security, do not share this code."
    return text


def render_preview(
    template: MessageTemplate,
    variables: Sequence[str] = (),
    *,
    header_variables: Sequence[str] = (),
) -> dict[str, Any]:
    """Rendered header, body, footer text and buttons.

    ``variables`` fill the body's ``{{n}}`` in order and ``header_variables`` a text header's.
    Missing values fall back to the template's example values, then stay as ``{{n}}``.
    """
    components = _components_by_type(template)
    body = components.get("BODY") or {}
    body_text = (
        _authentication_body(body) if _is_authentication(template) else str(body.get("text", ""))
    )
    if len(variables) > validators.variable_count(body_text):
        raise ValidationError(
            {
                "variables": [
                    f"The body has {validators.variable_count(body_text)} variable(s) but "
                    f"{len(variables)} value(s) were given."
                ]
            }
        )

    header_payload: dict[str, Any] | None = None
    header = components.get("HEADER")
    if header is not None:
        header_format = str(header.get("format", "")).upper()
        header_text = header.get("text") if header_format == validators.TEXT_HEADER else None
        if isinstance(header_text, str):
            header_text = _substitute(
                header_text, header_variables, _samples(header, "header_text")
            )
        header_payload = {"format": header_format, "text": header_text}

    footer_text: str | None = None
    footer = components.get("FOOTER")
    if footer is not None:
        if _is_authentication(template) and footer.get("code_expiration_minutes"):
            footer_text = f"This code expires in {footer['code_expiration_minutes']} minutes."
        elif isinstance(footer.get("text"), str):
            footer_text = footer["text"]

    buttons = []
    for button in _buttons(components):
        button_type = str(button.get("type", "")).upper()
        rendered: dict[str, Any] = {"type": button_type, "text": button.get("text") or ""}
        if button_type == "URL":
            rendered["url"] = _preview_url(button)
        elif button_type == "PHONE_NUMBER":
            rendered["phone_number"] = button.get("phone_number", "")
        elif button_type == "COPY_CODE":
            rendered["text"] = rendered["text"] or "Copy offer code"
        elif button_type == "OTP":
            rendered["text"] = rendered["text"] or "Copy code"
        buttons.append(rendered)

    return {
        "header": header_payload,
        "body": _substitute(body_text, variables, _samples(body, "body_text")),
        "footer": footer_text,
        "buttons": buttons,
    }


def _preview_url(button: Mapping[str, Any]) -> str:
    """A URL button's link; Meta's example for a variable URL is the full sample URL."""
    url = str(button.get("url", ""))
    example = button.get("example")
    sample = example[0] if isinstance(example, list) and example else example
    if "{{1}}" not in url or not isinstance(sample, str) or not sample:
        return url
    prefix = url.split("{{1}}", 1)[0]
    return sample if sample.startswith(prefix) else url.replace("{{1}}", sample)


def _text_parameters(values: Sequence[str]) -> list[dict[str, str]]:
    return [{"type": "text", "text": str(value)} for value in values]


def build_send_components(
    template: MessageTemplate,
    *,
    body_params: Sequence[str] = (),
    header_param: str | Mapping[str, Any] | None = None,
    button_params: Mapping[int, str] | None = None,
) -> dict[str, Any]:
    """The Cloud API ``template`` object for sending ``template``.

    - ``body_params``: one string per body variable, in order. AUTHENTICATION templates take one:
      the code.
    - ``header_param``: a string for a TEXT header with a variable, or the media object for
      IMAGE/VIDEO/DOCUMENT (``{"id": media_id}`` or ``{"link": url}``, optional ``filename``)
      and LOCATION (``{"latitude", "longitude", "name"?, "address"?}``) headers.
    - ``button_params``: by button index; required for URL buttons with a variable (the URL
      suffix), COPY_CODE buttons (the coupon code) and OTP buttons (the code, defaults to the
      body code); optional for QUICK_REPLY buttons (the payload returned on tap).
    """
    if template.status != Status.APPROVED:
        raise TemplateNotApproved(
            f"Template {template.name} ({template.language}) is {template.status.lower()}; "
            "only approved templates can be sent."
        )
    components = _components_by_type(template)
    button_params = dict(button_params or {})
    errors: dict[str, list[str]] = {}
    send_components: list[dict[str, Any]] = []

    header = components.get("HEADER")
    if header is not None and not _is_authentication(template):
        header_component = _header_parameters(header, header_param, errors)
        if header_component:
            send_components.append(header_component)
    elif header_param is not None:
        errors["header_param"] = ["This template has no header variable."]

    body = components.get("BODY") or {}
    expected = 1 if _is_authentication(template) else validators.variable_count(body.get("text"))
    if len(body_params) != expected:
        errors["body_params"] = [f"The body needs {expected} parameter(s), got {len(body_params)}."]
    elif expected:
        send_components.append({"type": "body", "parameters": _text_parameters(body_params)})

    buttons = _buttons(components)
    for index in button_params:
        if not isinstance(index, int) or not 0 <= index < len(buttons):
            errors.setdefault("button_params", []).append(f"There is no button at index {index}.")
    for index, button in enumerate(buttons):
        button_component = _button_parameters(index, button, button_params, body_params, errors)
        if button_component:
            send_components.append(button_component)

    if errors:
        raise ValidationError(errors)
    return {
        "name": template.name,
        "language": {"code": template.language},
        "components": send_components,
    }


def _header_parameters(
    header: Mapping[str, Any], header_param: Any, errors: dict[str, list[str]]
) -> dict[str, Any] | None:
    header_format = str(header.get("format", "")).upper()
    if header_format == validators.TEXT_HEADER:
        needs_param = validators.variable_count(header.get("text")) > 0
        if not needs_param:
            if header_param is not None:
                errors["header_param"] = ["This template's header has no variable."]
            return None
        if not isinstance(header_param, str) or not header_param:
            errors["header_param"] = ["The header needs one text parameter."]
            return None
        return {"type": "header", "parameters": _text_parameters([header_param])}

    kind = header_format.lower()
    if not isinstance(header_param, Mapping) or not header_param:
        errors["header_param"] = [f"The {kind} header needs a {kind} object."]
        return None
    if header_format == "LOCATION":
        if "latitude" not in header_param or "longitude" not in header_param:
            errors["header_param"] = ["The location header needs latitude and longitude."]
            return None
    elif not (header_param.get("id") or header_param.get("link")):
        errors["header_param"] = [f"The {kind} header needs a media id or link."]
        return None
    return {"type": "header", "parameters": [{"type": kind, kind: dict(header_param)}]}


def _button_parameters(
    index: int,
    button: Mapping[str, Any],
    button_params: Mapping[int, str],
    body_params: Sequence[str],
    errors: dict[str, list[str]],
) -> dict[str, Any] | None:
    button_type = str(button.get("type", "")).upper()
    value = button_params.get(index)

    def component(sub_type: str, parameter: dict[str, str]) -> dict[str, Any]:
        return {
            "type": "button",
            "sub_type": sub_type,
            "index": str(index),
            "parameters": [parameter],
        }

    def require(message: str) -> None:
        errors.setdefault("button_params", []).append(f"Button {index}: {message}")

    if button_type == "URL":
        if validators.variable_count(button.get("url")) == 0:
            if value is not None:
                require("this URL has no variable.")
            return None
        if not value:
            require("the URL needs a text parameter for its variable.")
            return None
        return component("url", {"type": "text", "text": str(value)})
    if button_type == "COPY_CODE":
        if not value:
            require("the copy code button needs a coupon code.")
            return None
        return component("copy_code", {"type": "coupon_code", "coupon_code": str(value)})
    if button_type == "OTP":
        code = value or (body_params[0] if body_params else None)
        if not code:
            require("the OTP button needs the code.")
            return None
        return component("url", {"type": "text", "text": str(code)})
    if button_type == "QUICK_REPLY":
        if value is None:
            return None
        return component("quick_reply", {"type": "payload", "payload": str(value)})
    if value is not None:
        require(f"{button_type} buttons take no parameters.")
    return None
