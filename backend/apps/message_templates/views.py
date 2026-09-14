import uuid

from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.whatsapp.models import WhatsAppBusinessAccount
from common.roles import Role
from common.routers import UUID_LOOKUP_REGEX
from common.tenancy import WorkspaceScopedMixin

from . import services, tasks
from .models import MessageTemplate
from .serializers import (
    MessageTemplateSerializer,
    PreviewRequestSerializer,
    PreviewSerializer,
    SyncQueuedSerializer,
    SyncRequestSerializer,
)


class MessageTemplateViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    """WhatsApp message templates of the header workspace.

    Created as local drafts, then submitted to Meta for review. Drafts and rejected templates can
    be edited; everything else is read-only until Meta changes its status.
    """

    queryset = MessageTemplate.objects.select_related("waba")
    serializer_class = MessageTemplateSerializer
    lookup_value_regex = UUID_LOOKUP_REGEX
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    filterset_fields = ("status", "category", "language", "waba")
    search_fields = ("name",)
    ordering_fields = ("created_at",)
    action_roles = {"submit": Role.ADMIN, "preview": Role.VIEWER, "sync": Role.ADMIN}

    def perform_create(self, serializer):
        serializer.instance = services.create_draft(
            workspace=self.workspace, created_by=self.request.user, **serializer.validated_data
        )

    def update(self, request, *args, **kwargs):
        if not self.get_object().is_editable:
            raise services.TemplateNotEditable()
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        serializer.instance = services.update_template(
            serializer.instance, **serializer.validated_data
        )

    def perform_destroy(self, instance):
        services.delete(instance)

    @extend_schema(request=None, responses={200: MessageTemplateSerializer})
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        """Send a draft or rejected template to Meta for review."""
        template = services.submit(self.get_object())
        return Response(
            MessageTemplateSerializer(template, context=self.get_serializer_context()).data
        )

    @extend_schema(request=PreviewRequestSerializer, responses={200: PreviewSerializer})
    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        """Render the template with body (and header) variables."""
        serializer = PreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rendered = services.render_preview(
            self.get_object(),
            serializer.validated_data["variables"],
            header_variables=serializer.validated_data["header_variables"],
        )
        return Response(PreviewSerializer(rendered).data)

    @extend_schema(request=SyncRequestSerializer, responses={202: SyncQueuedSerializer})
    @action(detail=False, methods=["post"])
    def sync(self, request):
        """Queue a sync from Meta for one account, or every active account in the workspace."""
        serializer = SyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        wabas = WhatsAppBusinessAccount.objects.filter(workspace=self.workspace)
        raw_id = serializer.validated_data.get("waba_id", "").strip()
        if raw_id:
            try:
                wabas = wabas.filter(pk=uuid.UUID(raw_id))
            except ValueError:
                wabas = wabas.filter(waba_id=raw_id)
            if not wabas.exists():
                raise exceptions.NotFound("WhatsApp Business Account not found.")
        else:
            wabas = wabas.filter(status=WhatsAppBusinessAccount.Status.ACTIVE)

        queued = [str(pk) for pk in wabas.values_list("pk", flat=True)]
        for waba_pk in queued:
            tasks.sync_waba.delay(waba_pk)
        return Response(
            SyncQueuedSerializer({"queued": queued}).data, status=status.HTTP_202_ACCEPTED
        )
