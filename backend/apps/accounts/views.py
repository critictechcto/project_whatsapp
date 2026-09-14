from django.contrib.auth import get_user_model
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import (
    TokenBlacklistView,
    TokenObtainPairView,
    TokenRefreshView,
)

from .serializers import (
    MeSerializer,
    PasswordChangeSerializer,
    RegisterResponseSerializer,
    RegisterSerializer,
    UserSerializer,
)

User = get_user_model()


class AuthThrottleMixin:
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "auth"


class RegisterView(AuthThrottleMixin, generics.GenericAPIView):
    serializer_class = RegisterSerializer
    permission_classes = (AllowAny,)
    authentication_classes = ()

    @extend_schema(responses={201: RegisterResponseSerializer})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        body = {
            "user": UserSerializer(user).data,
            "tokens": {"access": str(refresh.access_token), "refresh": str(refresh)},
        }
        return Response(body, status=status.HTTP_201_CREATED)


class LoginView(AuthThrottleMixin, TokenObtainPairView):
    """Exchange email + password for an access/refresh token pair."""


class RefreshView(AuthThrottleMixin, TokenRefreshView):
    """Rotate a refresh token. The old refresh token is blacklisted."""


class LogoutView(TokenBlacklistView):
    """Blacklist a refresh token."""


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = MeSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user


class PasswordChangeView(generics.GenericAPIView):
    serializer_class = PasswordChangeSerializer

    @extend_schema(responses={204: None})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        with transaction.atomic():
            user.set_password(serializer.validated_data["new_password"])
            user.save(update_fields=["password"])
            # Sign out every other session.
            for token in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=token)
        return Response(status=status.HTTP_204_NO_CONTENT)
