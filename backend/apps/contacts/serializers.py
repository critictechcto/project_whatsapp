from pathlib import PurePath

from django.conf import settings
from django.db.models import QuerySet
from rest_framework import serializers

from common.exceptions import Conflict
from common.phone import InvalidPhoneNumber, normalize_e164, to_wa_id

from .models import ConsentEvent, Contact, ContactImport, Tag

# Sources a user may claim when recording consent through the API.
CONSENT_REQUEST_SOURCES = [
    (ConsentEvent.Source.MANUAL.value, ConsentEvent.Source.MANUAL.label),
    (ConsentEvent.Source.API.value, ConsentEvent.Source.API.label),
]
MAX_ATTRIBUTES = 100
MAX_BULK_CONTACTS = 5000


def workspace_tags(context) -> QuerySet[Tag]:
    workspace = context.get("workspace")
    return Tag.objects.filter(workspace=workspace) if workspace else Tag.objects.none()


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ("id", "name", "color", "created_at")
        read_only_fields = ("id", "created_at")
        # Case-insensitive uniqueness is checked in validate() and reported as 409.
        validators: list = []

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        return value

    def validate(self, attrs: dict) -> dict:
        name = attrs.get("name")
        workspace = self.context.get("workspace")
        if name and workspace:
            clash = Tag.objects.filter(workspace=workspace, name__iexact=name)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise Conflict("A tag with this name already exists.")
        return attrs


class ContactSerializer(serializers.ModelSerializer):
    phone_e164 = serializers.CharField(
        max_length=32,
        help_text="Any common format; Indian local numbers are accepted. Stored as E.164.",
    )
    attributes = serializers.DictField(required=False)
    tags = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=Tag.objects.none()
    )

    class Meta:
        model = Contact
        fields = (
            "id",
            "phone_e164",
            "wa_id",
            "name",
            "email",
            "attributes",
            "tags",
            "marketing_opt_in_status",
            "opted_in_at",
            "opted_out_at",
            "opt_in_source",
            "last_inbound_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "wa_id",
            "marketing_opt_in_status",
            "opted_in_at",
            "opted_out_at",
            "opt_in_source",
            "last_inbound_at",
            "created_at",
            "updated_at",
        )
        validators: list = []

    def get_fields(self):
        fields = super().get_fields()
        fields["tags"].child_relation.queryset = workspace_tags(self.context)
        return fields

    def validate_phone_e164(self, value: str) -> str:
        try:
            return normalize_e164(value)
        except InvalidPhoneNumber as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_attributes(self, value: dict) -> dict:
        if len(value) > MAX_ATTRIBUTES:
            raise serializers.ValidationError(f"At most {MAX_ATTRIBUTES} attributes are allowed.")
        return value

    def validate(self, attrs: dict) -> dict:
        phone = attrs.get("phone_e164")
        workspace = self.context.get("workspace")
        if phone:
            attrs["wa_id"] = to_wa_id(phone)
            if workspace:
                clash = Contact.objects.filter(workspace=workspace, phone_e164=phone)
                if self.instance is not None:
                    clash = clash.exclude(pk=self.instance.pk)
                if clash.exists():
                    raise Conflict("A contact with this phone number already exists.")
        return attrs


class ConsentEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsentEvent
        fields = (
            "id",
            "purpose",
            "action",
            "source",
            "evidence",
            "actor",
            "wamid",
            "occurred_at",
            "created_at",
        )
        read_only_fields = fields


class ConsentRequestSerializer(serializers.Serializer):
    source = serializers.ChoiceField(
        choices=CONSENT_REQUEST_SOURCES, default=ConsentEvent.Source.MANUAL.value
    )
    evidence = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class OptInRequestSerializer(ConsentRequestSerializer):
    evidence = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=2000,
        help_text="How and when the customer agreed to receive marketing messages. Required.",
    )

    def validate(self, attrs: dict) -> dict:
        # Every source accepted here (manual, api) needs evidence of consent.
        attrs["evidence"] = attrs.get("evidence", "").strip()
        if not attrs["evidence"]:
            raise serializers.ValidationError({"evidence": ["Describe how the customer opted in."]})
        return attrs


class BulkTagSerializer(serializers.Serializer):
    contact_ids = serializers.ListField(
        child=serializers.UUIDField(), min_length=1, max_length=MAX_BULK_CONTACTS
    )
    add_tag_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    remove_tag_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )

    def validate(self, attrs: dict) -> dict:
        workspace = self.context["workspace"]
        attrs["contact_ids"] = set(attrs["contact_ids"])
        attrs["add_tag_ids"] = set(attrs["add_tag_ids"])
        attrs["remove_tag_ids"] = set(attrs["remove_tag_ids"])
        if not attrs["add_tag_ids"] and not attrs["remove_tag_ids"]:
            raise serializers.ValidationError("Pass add_tag_ids and/or remove_tag_ids.")
        if attrs["add_tag_ids"] & attrs["remove_tag_ids"]:
            raise serializers.ValidationError("A tag can't be both added and removed.")

        errors = {}
        known_contacts = set(
            Contact.objects.filter(workspace=workspace, pk__in=attrs["contact_ids"]).values_list(
                "pk", flat=True
            )
        )
        if missing := attrs["contact_ids"] - known_contacts:
            errors["contact_ids"] = [f"Unknown contact ids: {sorted(map(str, missing))}"]
        for key in ("add_tag_ids", "remove_tag_ids"):
            known = set(
                Tag.objects.filter(workspace=workspace, pk__in=attrs[key]).values_list(
                    "pk", flat=True
                )
            )
            if missing := attrs[key] - known:
                errors[key] = [f"Unknown tag ids: {sorted(map(str, missing))}"]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class BulkTagResultSerializer(serializers.Serializer):
    contact_count = serializers.IntegerField()
    added = serializers.IntegerField(help_text="Tag links created.")
    removed = serializers.IntegerField(help_text="Tag links removed.")


class ImportRowErrorSerializer(serializers.Serializer):
    row = serializers.IntegerField(allow_null=True, help_text="1-based CSV line; null if global.")
    error = serializers.CharField()


class ContactImportSerializer(serializers.ModelSerializer):
    file_name = serializers.SerializerMethodField()
    errors = ImportRowErrorSerializer(many=True, read_only=True)

    class Meta:
        model = ContactImport
        fields = (
            "id",
            "file_name",
            "status",
            "total_rows",
            "created_count",
            "updated_count",
            "skipped_count",
            "error_count",
            "errors",
            "mark_opted_in",
            "consent_attested",
            "opt_in_source",
            "tags",
            "created_by",
            "started_at",
            "finished_at",
            "created_at",
        )
        read_only_fields = fields

    def get_file_name(self, obj: ContactImport) -> str:
        return PurePath(obj.file.name).name if obj.file else ""


class ContactImportCreateSerializer(serializers.ModelSerializer):
    file = serializers.FileField(help_text="UTF-8 CSV with a phone column.")
    tag_ids = serializers.PrimaryKeyRelatedField(
        many=True, required=False, source="tags", queryset=Tag.objects.none()
    )
    opt_in_source = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text="Where these contacts opted in, e.g. 'Checkout form on example.in'.",
    )

    class Meta:
        model = ContactImport
        fields = ("file", "mark_opted_in", "consent_attested", "opt_in_source", "tag_ids")

    def get_fields(self):
        fields = super().get_fields()
        fields["tag_ids"].child_relation.queryset = workspace_tags(self.context)
        return fields

    def validate_file(self, value):
        max_bytes = getattr(settings, "CONTACT_IMPORT_MAX_BYTES", 10 * 1024 * 1024)
        if value.size > max_bytes:
            raise serializers.ValidationError(
                f"The file is larger than the {max_bytes // (1024 * 1024) or 1} MB limit."
            )
        if not value.name.lower().endswith(".csv"):
            raise serializers.ValidationError("Upload a .csv file.")
        return value

    def validate(self, attrs: dict) -> dict:
        attrs["opt_in_source"] = attrs.get("opt_in_source", "").strip()
        if attrs.get("mark_opted_in"):
            errors = {}
            if not attrs.get("consent_attested"):
                errors["consent_attested"] = [
                    "Confirm these contacts agreed to receive marketing messages."
                ]
            if not attrs["opt_in_source"]:
                errors["opt_in_source"] = ["Say where these contacts opted in."]
            if errors:
                raise serializers.ValidationError(errors)
        return attrs
