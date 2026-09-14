from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response

from common.roles import Role
from common.routers import UUID_LOOKUP_REGEX
from common.tenancy import WorkspaceScopedAPIView, WorkspaceScopedGenericViewSet

from . import services
from .models import PhoneNumber, WhatsAppBusinessAccount
from .serializers import (
    EmbeddedSignupSerializer,
    PhoneNumberSerializer,
    SignupConfigSerializer,
    WhatsAppBusinessAccountSerializer,
)


def _account_queryset():
    return WhatsAppBusinessAccount.objects.prefetch_related("phone_numbers")


class SignupConfigView(WorkspaceScopedAPIView):
    """Public Meta app settings the frontend needs to launch Embedded Signup."""

    queryset = WhatsAppBusinessAccount.objects.all()
    serializer_class = SignupConfigSerializer
    read_role = Role.VIEWER

    @extend_schema(responses={200: SignupConfigSerializer})
    def get(self, request):
        self.membership  # noqa: B018 - resolves the workspace (404 for non-members)
        body = SignupConfigSerializer(
            {
                "app_id": settings.META_APP_ID,
                "config_id": settings.META_EMBEDDED_SIGNUP_CONFIG_ID,
                "graph_api_version": settings.META_GRAPH_API_VERSION,
            }
        ).data
        return Response(body)


class EmbeddedSignupView(WorkspaceScopedAPIView):
    """Finish Embedded Signup with the code and ids from the frontend's session-info event."""

    queryset = WhatsAppBusinessAccount.objects.all()
    serializer_class = EmbeddedSignupSerializer
    write_role = Role.ADMIN

    @extend_schema(
        request=EmbeddedSignupSerializer, responses={201: WhatsAppBusinessAccountSerializer}
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        waba = services.complete_embedded_signup(
            workspace=self.workspace,
            user=request.user,
            code=data["code"],
            waba_id=data["waba_id"],
            phone_number_id=data.get("phone_number_id") or None,
            business_id=data.get("business_id") or "",
            coexistence=data.get("coexistence", False),
        )
        body = WhatsAppBusinessAccountSerializer(
            _account_queryset().get(pk=waba.pk), context=self.get_serializer_context()
        ).data
        return Response(body, status=status.HTTP_201_CREATED)


class WhatsAppBusinessAccountViewSet(
    WorkspaceScopedGenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
):
    """Connected WhatsApp Business Accounts. Deleting one disconnects it."""

    queryset = _account_queryset()
    serializer_class = WhatsAppBusinessAccountSerializer
    lookup_value_regex = UUID_LOOKUP_REGEX
    filterset_fields = ("status", "onboarding_status")
    ordering_fields = ("created_at",)
    write_role = Role.ADMIN

    @extend_schema(responses={204: None})
    def destroy(self, request, *args, **kwargs):
        services.disconnect_waba(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=None, responses={202: WhatsAppBusinessAccountSerializer})
    @action(detail=True, methods=["post"])
    def resync(self, request, pk=None):
        services.resync_waba(self.get_object())
        waba = self.get_queryset().get(pk=pk)
        return Response(self.get_serializer(waba).data, status=status.HTTP_202_ACCEPTED)


class PhoneNumberViewSet(
    WorkspaceScopedGenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
):
    queryset = PhoneNumber.objects.select_related("waba")
    serializer_class = PhoneNumberSerializer
    lookup_value_regex = UUID_LOOKUP_REGEX
    filterset_fields = ("waba", "registration_status", "quality_rating", "is_default")
    ordering_fields = ("created_at",)
    write_role = Role.ADMIN

    @extend_schema(request=None, responses={200: PhoneNumberSerializer})
    @action(detail=True, methods=["post"])
    def refresh(self, request, pk=None):
        phone = services.refresh_phone_number_now(self.get_object())
        return Response(self.get_serializer(phone).data)

    @extend_schema(request=None, responses={202: PhoneNumberSerializer})
    @action(detail=True, methods=["post"], url_path="retry-registration")
    def retry_registration(self, request, pk=None):
        phone = services.retry_registration(self.get_object())
        return Response(self.get_serializer(phone).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(request=None, responses={200: PhoneNumberSerializer})
    @action(detail=True, methods=["post"], url_path="set-default")
    def set_default(self, request, pk=None):
        phone = services.set_default_phone_number(self.get_object())
        return Response(self.get_serializer(phone).data)
