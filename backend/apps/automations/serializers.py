"""Automation API shapes (docs/contracts/wave-2.md). ``FooSerializer`` makes component ``Foo``."""

from rest_framework import serializers

from .schema_enums import (
    AUTOMATION_ACTION_TYPES,
    AUTOMATION_RUN_STATUSES,
    AUTOMATION_TRIGGERS,
    KEYWORD_MATCHES,
)

MAX_ACTIONS = 5
MAX_KEYWORDS = 50
TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"

# Keys each action type needs in ``config``.
ACTION_CONFIG_KEYS = {
    "send_text": ("text",),
    "send_template": ("template_id",),
    "add_tags": ("tag_ids",),
    "assign": ("user_id",),
    "close_conversation": (),
}


class AutomationActionSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=AUTOMATION_ACTION_TYPES)
    config = serializers.DictField(
        default=dict,
        help_text=(
            "send_text {text}; send_template {template_id, body_params: VariableSource[]}; "
            "add_tags {tag_ids}; assign {user_id}; close_conversation {}."
        ),
    )

    def validate(self, attrs: dict) -> dict:
        missing = [key for key in ACTION_CONFIG_KEYS[attrs["type"]] if key not in attrs["config"]]
        if missing:
            raise serializers.ValidationError(
                {"config": [f"{attrs['type']} needs: {', '.join(missing)}."]}
            )
        return attrs


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

    def validate(self, attrs: dict) -> dict:
        trigger = attrs.get("trigger", getattr(self.instance, "trigger", None))
        if trigger == "keyword" and "keywords" in attrs:
            attrs["keywords"] = [word.strip() for word in attrs["keywords"] if word.strip()]
            if not attrs["keywords"]:
                raise serializers.ValidationError(
                    {"keywords": ["Add at least one keyword for the keyword trigger."]}
                )
        elif trigger == "keyword" and not self.partial:
            raise serializers.ValidationError(
                {"keywords": ["Add at least one keyword for the keyword trigger."]}
            )
        return attrs


class BusinessHoursSlotSerializer(serializers.Serializer):
    day = serializers.IntegerField(min_value=0, max_value=6, help_text="0 = Monday … 6 = Sunday.")
    start = serializers.RegexField(TIME_PATTERN, help_text="HH:MM")
    end = serializers.RegexField(
        TIME_PATTERN, help_text="HH:MM. Earlier than start means the slot runs overnight."
    )


class BusinessHoursSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    time_zone = serializers.CharField(read_only=True, help_text="The workspace time zone.")
    schedule = BusinessHoursSlotSerializer(many=True, max_length=50)


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
