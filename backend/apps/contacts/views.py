from django.db import IntegrityError, transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from common.exceptions import Conflict
from common.roles import Role
from common.routers import UUID_LOOKUP_REGEX
from common.tenancy import WorkspaceScopedMixin, WorkspaceScopedViewSet

from . import services
from .filters import ContactFilter
from .models import ConsentEvent, Contact, ContactImport, Tag
from .serializers import (
    BulkTagResultSerializer,
    BulkTagSerializer,
    ConsentEventSerializer,
    ConsentRequestSerializer,
    ContactImportCreateSerializer,
    ContactImportSerializer,
    ContactSerializer,
    OptInRequestSerializer,
    TagSerializer,
)
from .tasks import import_csv


class UniqueConflictMixin:
    """Turn a unique-constraint race on save into 409 (serializers pre-check the common case)."""

    conflict_message = "This conflicts with an existing record."

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                super().perform_create(serializer)
        except IntegrityError as exc:
            raise Conflict(self.conflict_message) from exc

    def perform_update(self, serializer):
        try:
            with transaction.atomic():
                super().perform_update(serializer)
        except IntegrityError as exc:
            raise Conflict(self.conflict_message) from exc


class TagViewSet(UniqueConflictMixin, WorkspaceScopedViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    lookup_value_regex = UUID_LOOKUP_REGEX
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    read_role = Role.VIEWER
    write_role = Role.AGENT
    search_fields = ("name",)
    ordering_fields = ("created_at",)
    conflict_message = "A tag with this name already exists."


class ContactViewSet(UniqueConflictMixin, WorkspaceScopedViewSet):
    """Contacts of the header workspace. Consent changes only through opt-in/opt-out."""

    queryset = Contact.objects.prefetch_related("tags")
    serializer_class = ContactSerializer
    lookup_value_regex = UUID_LOOKUP_REGEX
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    read_role = Role.VIEWER
    write_role = Role.AGENT
    action_roles = {
        "destroy": Role.ADMIN,
        "consent_events": Role.VIEWER,
        "opt_in": Role.AGENT,
        "opt_out": Role.AGENT,
        "bulk_tag": Role.AGENT,
    }
    filterset_class = ContactFilter
    search_fields = ("name", "phone_e164", "email")
    ordering_fields = ("created_at",)
    conflict_message = "A contact with this phone number already exists."

    @extend_schema(responses=ConsentEventSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="consent-events", filter_backends=[])
    def consent_events(self, request, pk=None):
        contact = self.get_object()
        queryset = ConsentEvent.objects.filter(contact=contact).select_related("actor")
        page = self.paginate_queryset(queryset)
        serializer = ConsentEventSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(request=OptInRequestSerializer, responses=ContactSerializer)
    @action(detail=True, methods=["post"], url_path="opt-in", filter_backends=[])
    def opt_in(self, request, pk=None):
        contact = self.get_object()
        body = OptInRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.record_opt_in(
            contact,
            source=body.validated_data["source"],
            actor=request.user,
            evidence=body.validated_data["evidence"].strip(),
        )
        return Response(self.get_serializer(contact).data)

    @extend_schema(request=ConsentRequestSerializer, responses=ContactSerializer)
    @action(detail=True, methods=["post"], url_path="opt-out", filter_backends=[])
    def opt_out(self, request, pk=None):
        contact = self.get_object()
        body = ConsentRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.record_opt_out(
            contact,
            source=body.validated_data["source"],
            actor=request.user,
            evidence=body.validated_data.get("evidence", "").strip(),
        )
        return Response(self.get_serializer(contact).data)

    @extend_schema(request=BulkTagSerializer, responses=BulkTagResultSerializer)
    @action(detail=False, methods=["post"], url_path="bulk-tag", filter_backends=[])
    def bulk_tag(self, request):
        body = BulkTagSerializer(data=request.data, context=self.get_serializer_context())
        body.is_valid(raise_exception=True)
        contact_ids = body.validated_data["contact_ids"]
        add_tag_ids = body.validated_data["add_tag_ids"]
        remove_tag_ids = body.validated_data["remove_tag_ids"]
        through = Contact.tags.through

        with transaction.atomic():
            removed = 0
            if remove_tag_ids:
                removed, _ = through.objects.filter(
                    contact_id__in=contact_ids, tag_id__in=remove_tag_ids
                ).delete()
            existing = set(
                through.objects.filter(
                    contact_id__in=contact_ids, tag_id__in=add_tag_ids
                ).values_list("contact_id", "tag_id")
            )
            links = [
                through(contact_id=contact_id, tag_id=tag_id)
                for contact_id in contact_ids
                for tag_id in add_tag_ids
                if (contact_id, tag_id) not in existing
            ]
            through.objects.bulk_create(links, ignore_conflicts=True)
            Contact.objects.filter(workspace=self.workspace, pk__in=contact_ids).update(
                updated_at=timezone.now()
            )

        result = {"contact_count": len(contact_ids), "added": len(links), "removed": removed}
        return Response(BulkTagResultSerializer(result).data)


class ContactImportViewSet(
    WorkspaceScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """CSV contact imports. Uploading starts a background import."""

    queryset = ContactImport.objects.prefetch_related("tags")
    serializer_class = ContactImportSerializer
    lookup_value_regex = UUID_LOOKUP_REGEX
    read_role = Role.AGENT
    write_role = Role.ADMIN
    ordering_fields = ("created_at",)
    parser_classes = (MultiPartParser, FormParser)

    def get_serializer_class(self):
        if self.action == "create":
            return ContactImportCreateSerializer
        return ContactImportSerializer

    @extend_schema(
        request={"multipart/form-data": ContactImportCreateSerializer},
        responses={201: ContactImportSerializer},
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            job = serializer.save(
                workspace=self.workspace,
                created_by=request.user,
                status=ContactImport.Status.QUEUED,
            )
            job_pk = str(job.pk)
            transaction.on_commit(lambda: import_csv.delay(job_pk))
        body = ContactImportSerializer(job, context=self.get_serializer_context()).data
        return Response(body, status=status.HTTP_201_CREATED)
