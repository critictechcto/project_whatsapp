"""Automation API shapes (docs/contracts/wave-2.md). ``FooSerializer`` makes component ``Foo``.

Action configs are validated against the request's workspace and stored normalised:

- ``send_text {text}``: non-blank, at most 4096 characters.
- ``send_template {template_id, body_params}``: a template of this workspace (on the rule's
  number's WABA when the rule has a number) whose body placeholders match ``body_params``, and
  which needs no header or button parameters. ``body_params`` are VariableSources.
- ``add_tags {tag_ids}``: 1-50 tags of this workspace.
- ``assign {user_id}``: a member of this workspace.
- ``close_conversation {}``.
- ``send_shop_menu {}`` and ``send_catalog {}``: commerce sends run by ``apps.shop``.
- ``send_collection {collection_id}``: a UUID. The collection is looked up when the rule runs; a
  missing collection fails that action.
"""

import copy
import uuid
from collections.abc import Mapping
from typing import Any

from rest_framework import serializers

from apps.contacts.models import Tag
from apps.message_templates import services as template_services
from apps.message_templates import validators as template_validators
from apps.message_templates.models import MessageTemplate
from apps.tenants.models import Membership
from apps.whatsapp.models import PhoneNumber

from . import business_hours, matching
from .engine import CONTACT_FIELDS
from .models import AutomationRule, BusinessHours
from .schema_enums import (
    AUTOMATION_ACTION_TYPES,
    AUTOMATION_RUN_STATUSES,
    AUTOMATION_TRIGGERS,
    KEYWORD_MATCHES,
)

MAX_ACTIONS = 5
MAX_KEYWORDS = 50
MAX_TAGS_PER_ACTION = 50
MAX_TEXT_LENGTH = 4096
MAX_VARIABLE_LENGTH = 1024
TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
VARIABLE_SOURCE_TYPES = ("contact_field", "attribute", "static")

# Keys each action type needs in ``config``.
ACTION_CONFIG_KEYS = {
    "send_text": ("text",),
    "send_template": ("template_id",),
    "add_tags": ("tag_ids",),
    "assign": ("user_id",),
    "close_conversation": (),
    "send_shop_menu": (),
    "send_catalog": (),
    "send_collection": ("collection_id",),
}

KEYWORDS_REQUIRED = "Add at least one keyword for the keyword trigger."
TEMPLATE_WABA_MISMATCH = (
    "The template belongs to a different WhatsApp Business Account than the rule's number."
)


def _workspace(serializer: serializers.Serializer):
    workspace = serializer.context.get("workspace")
    if workspace is None:  # pragma: no cover - views always pass it
        raise RuntimeError("Automation serializers need the workspace in their context.")
    return workspace


def _as_uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


class ConfigError(Exception):
    def __init__(self, errors: dict[str, list[str]]) -> None:
        super().__init__(errors)
        self.errors = errors


# --- Action configs -----------------------------------------------------------------------------


def _clean_send_text(workspace, config: Mapping[str, Any]) -> dict[str, Any]:
    text = config.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ConfigError({"text": ["Enter the message text."]})
    text = text.strip()
    if len(text) > MAX_TEXT_LENGTH:
        raise ConfigError(
            {"text": [f"Ensure this field has no more than {MAX_TEXT_LENGTH} characters."]}
        )
    return {"text": text}


def _clean_variable_source(raw: Any) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        raise ValueError("Each body parameter must be an object with source and value.")
    source, value, fallback = raw.get("source"), raw.get("value", ""), raw.get("fallback", "")
    if source not in VARIABLE_SOURCE_TYPES:
        raise ValueError(f"source must be one of: {', '.join(VARIABLE_SOURCE_TYPES)}.")
    if not isinstance(value, str) or not isinstance(fallback, str):
        raise ValueError("value and fallback must be strings.")
    value, fallback = value.strip(), fallback.strip()
    if len(value) > MAX_VARIABLE_LENGTH or len(fallback) > MAX_VARIABLE_LENGTH:
        raise ValueError(f"value and fallback may have at most {MAX_VARIABLE_LENGTH} characters.")
    if source == "contact_field" and value not in CONTACT_FIELDS:
        raise ValueError(f"A contact field must be one of: {', '.join(CONTACT_FIELDS)}.")
    if source == "attribute" and not value:
        raise ValueError("Enter the contact attribute key.")
    if source == "static" and not value and not fallback:
        raise ValueError("Enter the static text.")
    return {"source": source, "value": value, "fallback": fallback}


def expected_body_params(template: MessageTemplate) -> int:
    if template.category == MessageTemplate.Category.AUTHENTICATION:
        return 1
    for component in template.components or ():
        if isinstance(component, Mapping) and str(component.get("type", "")).upper() == "BODY":
            return template_validators.variable_count(component.get("text"))
    return 0


def _clean_send_template(workspace, config: Mapping[str, Any]) -> dict[str, Any]:
    template_id = _as_uuid(config.get("template_id"))
    template = (
        MessageTemplate.objects.filter(workspace=workspace, pk=template_id).first()
        if template_id
        else None
    )
    if template is None:
        raise ConfigError({"template_id": ["Choose a template from this workspace."]})

    raw_params = config.get("body_params", [])
    if not isinstance(raw_params, list):
        raise ConfigError({"body_params": ["Send a list of variable sources."]})
    params, param_errors = [], []
    for position, raw in enumerate(raw_params, start=1):
        try:
            params.append(_clean_variable_source(raw))
        except ValueError as exc:
            param_errors.append(f"Parameter {position}: {exc}")
    if param_errors:
        raise ConfigError({"body_params": param_errors})

    expected = expected_body_params(template)
    if len(params) != expected:
        raise ConfigError(
            {
                "body_params": [
                    f"The template body has {expected} variable(s) but {len(params)} "
                    "parameter(s) were given."
                ]
            }
        )
    # Probe with placeholder values: header and button variables can't be filled by automations.
    probe = copy.copy(template)
    probe.status = MessageTemplate.Status.APPROVED
    try:
        template_services.build_send_components(probe, body_params=["x"] * expected)
    except serializers.ValidationError as exc:
        extra = {key for key in exc.detail if key != "body_params"}
        if extra:
            raise ConfigError(
                {
                    "template_id": [
                        "This template needs header or button parameters, which automations "
                        "can't fill. Choose a template that only uses body variables."
                    ]
                }
            ) from exc
        raise
    return {"template_id": str(template.pk), "body_params": params}


def _clean_add_tags(workspace, config: Mapping[str, Any]) -> dict[str, Any]:
    raw = config.get("tag_ids")
    if not isinstance(raw, list) or not raw:
        raise ConfigError({"tag_ids": ["Choose at least one tag."]})
    if len(raw) > MAX_TAGS_PER_ACTION:
        raise ConfigError({"tag_ids": [f"Choose at most {MAX_TAGS_PER_ACTION} tags."]})
    ids = [_as_uuid(value) for value in raw]
    if None in ids:
        raise ConfigError({"tag_ids": ["Tag ids must be UUIDs."]})
    unique_ids = list(dict.fromkeys(ids))
    found = set(
        Tag.objects.filter(workspace=workspace, pk__in=unique_ids).values_list("pk", flat=True)
    )
    if len(found) != len(unique_ids):
        raise ConfigError({"tag_ids": ["Every tag must belong to this workspace."]})
    return {"tag_ids": [str(tag_id) for tag_id in unique_ids]}


def _clean_assign(workspace, config: Mapping[str, Any]) -> dict[str, Any]:
    user_id = _as_uuid(config.get("user_id"))
    if (
        user_id is None
        or not Membership.objects.filter(workspace=workspace, user_id=user_id).exists()
    ):
        raise ConfigError({"user_id": ["The assignee must be a member of this workspace."]})
    return {"user_id": str(user_id)}


def _clean_close(workspace, config: Mapping[str, Any]) -> dict[str, Any]:
    return {}


def _clean_send_collection(workspace, config: Mapping[str, Any]) -> dict[str, Any]:
    collection_id = _as_uuid(config.get("collection_id"))
    if collection_id is None:
        raise ConfigError({"collection_id": ["Choose a collection from your store."]})
    return {"collection_id": str(collection_id)}


CONFIG_CLEANERS = {
    "send_text": _clean_send_text,
    "send_template": _clean_send_template,
    "add_tags": _clean_add_tags,
    "assign": _clean_assign,
    "close_conversation": _clean_close,
    "send_shop_menu": _clean_close,
    "send_catalog": _clean_close,
    "send_collection": _clean_send_collection,
}


# --- Serializers --------------------------------------------------------------------------------


class AutomationActionSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=AUTOMATION_ACTION_TYPES)
    config = serializers.DictField(
        default=dict,
        help_text=(
            "send_text {text}; send_template {template_id, body_params: VariableSource[]}; "
            "add_tags {tag_ids}; assign {user_id}; close_conversation {}; send_shop_menu {}; "
            "send_catalog {}; send_collection {collection_id}."
        ),
    )

    def validate(self, attrs: dict) -> dict:
        missing = [key for key in ACTION_CONFIG_KEYS[attrs["type"]] if key not in attrs["config"]]
        if missing:
            raise serializers.ValidationError(
                {"config": [f"{attrs['type']} needs: {', '.join(missing)}."]}
            )
        try:
            config = CONFIG_CLEANERS[attrs["type"]](_workspace(self), attrs["config"])
        except ConfigError as exc:
            raise serializers.ValidationError({"config": exc.errors}) from exc
        return {"type": attrs["type"], "config": config}


class AutomationRuleSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(max_length=120)
    is_active = serializers.BooleanField(default=True)
    trigger = serializers.ChoiceField(choices=AUTOMATION_TRIGGERS)
    keywords = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        default=list,
        max_length=MAX_KEYWORDS,
        help_text="Required for the keyword trigger. Matching ignores case.",
    )
    keyword_match = serializers.ChoiceField(choices=KEYWORD_MATCHES, default="exact")
    phone_number_id = serializers.UUIDField(
        required=False, allow_null=True, help_text="Null applies to every number."
    )
    actions = AutomationActionSerializer(many=True, min_length=1, max_length=MAX_ACTIONS)
    cooldown_minutes = serializers.IntegerField(min_value=0, default=0)
    priority = serializers.IntegerField(default=0, help_text="Lower runs first.")
    stop_processing = serializers.BooleanField(
        default=False, help_text="Skip lower-priority rules after this one runs."
    )
    run_count = serializers.IntegerField(read_only=True)
    last_triggered_at = serializers.DateTimeField(read_only=True, allow_null=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def validate_phone_number_id(self, value: uuid.UUID | None) -> uuid.UUID | None:
        if (
            value is not None
            and not PhoneNumber.objects.filter(workspace=_workspace(self), pk=value).exists()
        ):
            raise serializers.ValidationError("Choose a WhatsApp number from this workspace.")
        return value

    def validate_keywords(self, value: list[str]) -> list[str]:
        return matching.normalize_keywords(value)

    def validate(self, attrs: dict) -> dict:
        instance: AutomationRule | None = self.instance
        trigger = attrs.get("trigger", getattr(instance, "trigger", None))
        keywords = attrs.get("keywords", getattr(instance, "keywords", None) or [])
        if trigger == AutomationRule.Trigger.KEYWORD and not keywords:
            raise serializers.ValidationError({"keywords": [KEYWORDS_REQUIRED]})

        if "actions" in attrs or "phone_number_id" in attrs:
            phone_number_id = attrs.get(
                "phone_number_id", getattr(instance, "phone_number_id", None)
            )
            actions = attrs["actions"] if "actions" in attrs else getattr(instance, "actions", [])
            self._check_template_numbers(actions or [], phone_number_id)
        return attrs

    def _check_template_numbers(self, actions: list[dict], phone_number_id) -> None:
        """Templates in a rule scoped to one number must be on that number's WABA."""
        if phone_number_id is None:
            return
        waba_id = (
            PhoneNumber.objects.filter(pk=phone_number_id).values_list("waba_id", flat=True).first()
        )
        errors: list[dict] = []
        for action in actions:
            template_waba_id = None
            if action.get("type") == "send_template":
                template_id = _as_uuid((action.get("config") or {}).get("template_id"))
                template_waba_id = (
                    MessageTemplate.objects.filter(pk=template_id)
                    .values_list("waba_id", flat=True)
                    .first()
                )
            if template_waba_id is not None and template_waba_id != waba_id:
                errors.append({"config": {"template_id": [TEMPLATE_WABA_MISMATCH]}})
            else:
                errors.append({})
        if any(errors):
            raise serializers.ValidationError({"actions": errors})

    def create(self, validated_data: dict) -> AutomationRule:
        return AutomationRule.objects.create(**validated_data)

    def update(self, instance: AutomationRule, validated_data: dict) -> AutomationRule:
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance


class BusinessHoursSlotSerializer(serializers.Serializer):
    day = serializers.IntegerField(min_value=0, max_value=6, help_text="0 = Monday … 6 = Sunday.")
    start = serializers.RegexField(TIME_PATTERN, help_text="HH:MM")
    end = serializers.RegexField(
        TIME_PATTERN, help_text="HH:MM. Earlier than start means the slot runs overnight."
    )

    def validate(self, attrs: dict) -> dict:
        error = business_hours.slot_error(attrs)
        if error:
            raise serializers.ValidationError(error)
        return attrs


class BusinessHoursSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    time_zone = serializers.CharField(read_only=True, help_text="The workspace time zone.")
    schedule = BusinessHoursSlotSerializer(many=True, max_length=50)

    def update(self, instance: BusinessHours, validated_data: dict) -> BusinessHours:
        if "enabled" in validated_data:
            instance.enabled = validated_data["enabled"]
        if "schedule" in validated_data:
            instance.schedule = sorted(
                (
                    {"day": slot["day"], "start": slot["start"], "end": slot["end"]}
                    for slot in validated_data["schedule"]
                ),
                key=lambda slot: (slot["day"], slot["start"], slot["end"]),
            )
        instance.save()
        return instance


class AutomationRuleRefSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)


class AutomationRunSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    rule = AutomationRuleRefSerializer(read_only=True)
    conversation_id = serializers.UUIDField(read_only=True)
    message_id = serializers.UUIDField(read_only=True)
    status = serializers.ChoiceField(choices=AUTOMATION_RUN_STATUSES, read_only=True)
    detail = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
