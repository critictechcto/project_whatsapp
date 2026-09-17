import contextlib
import hashlib

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenViewBase

from .cookies import (
    AUTH_HEADER,
    REFRESH_COOKIE_NAME,
    check_cookie_request,
    clear_refresh_cookie,
    read_refresh_cookie,
    set_refresh_cookie,
)
from .serializers import (
    AccessTokenSerializer,
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


class LoginEmailThrottle(SimpleRateThrottle):
    """Limit login attempts per email address, whatever the client's IP.

    The ``auth`` scope throttles per client IP, which a password-guessing client can rotate: DRF
    takes the IP from ``X-Forwarded-For`` (client-controlled unless ``NUM_PROXIES`` is set).
    Keying on the submitted email caps guesses against one account regardless. The rate is
    ``DEFAULT_THROTTLE_RATES["login_email"]`` when set, else :attr:`default_rate`.
    """

    scope = "login_email"
    default_rate = "30/hour"

    def get_rate(self):
        return self.THROTTLE_RATES.get(self.scope, self.default_rate)

    def get_cache_key(self, request, view):
        data = request.data
        email = data.get("email") if hasattr(data, "get") else None
        if not isinstance(email, str) or not email.strip():
            return None
        ident = hashlib.sha256(email.strip().lower().encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": ident}


COOKIE_SET_NOTE = (
    f"Sets the refresh token in the `{REFRESH_COOKIE_NAME}` cookie (HttpOnly, SameSite=Strict, "
    "Path=/api/v1/auth/). The body carries the access token only."
)

REFRESH_COOKIE_PARAMETER = OpenApiParameter(
    REFRESH_COOKIE_NAME,
    OpenApiTypes.STR,
    location=OpenApiParameter.COOKIE,
    required=False,
    description="HttpOnly refresh token cookie set by login or register (sent by the browser).",
)
AUTH_HEADER_PARAMETER = OpenApiParameter(
    AUTH_HEADER,
    OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=True,
    enum=["1"],
    description="CSRF guard for the cookie endpoints: must be `1` (forces a CORS preflight).",
)
COOKIE_CSRF_403 = OpenApiResponse(
    description="Missing `X-UpChatz-Auth` header or a disallowed `Origin`."
)


class RegisterView(AuthThrottleMixin, generics.GenericAPIView):
    serializer_class = RegisterSerializer
    permission_classes = (AllowAny,)
    authentication_classes = ()

    @extend_schema(responses={201: RegisterResponseSerializer}, description=COOKIE_SET_NOTE)
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        body = {"user": UserSerializer(user).data, "access": str(refresh.access_token)}
        response = Response(body, status=status.HTTP_201_CREATED)
        set_refresh_cookie(response, str(refresh))
        return response


class LoginView(AuthThrottleMixin, TokenObtainPairView):
    """Exchange email + password for an access token; the refresh token goes in a cookie."""

    throttle_classes = (ScopedRateThrottle, LoginEmailThrottle)

    @extend_schema(responses={200: AccessTokenSerializer}, description=COOKIE_SET_NOTE)
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc
        data = serializer.validated_data
        response = Response({"access": data["access"]}, status=status.HTTP_200_OK)
        set_refresh_cookie(response, data["refresh"])
        return response


class RefreshView(AuthThrottleMixin, TokenViewBase):
    """Rotate the refresh cookie and return a new access token."""

    serializer_class = TokenRefreshSerializer

    @extend_schema(
        request=None,
        parameters=[AUTH_HEADER_PARAMETER, REFRESH_COOKIE_PARAMETER],
        responses={
            200: AccessTokenSerializer,
            401: OpenApiResponse(description="No refresh cookie, or it is invalid or reused."),
            403: COOKIE_CSRF_403,
        },
        description=(
            "Rotates the refresh token from the cookie: the old token is blacklisted and a new "
            "cookie is set. Any failure clears the cookie."
        ),
    )
    def post(self, request, *args, **kwargs):
        check_cookie_request(request)
        token = read_refresh_cookie(request)
        if not token:
            raise exceptions.NotAuthenticated("No refresh session.")
        serializer = self.get_serializer(data={"refresh": token})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc
        except ObjectDoesNotExist as exc:
            raise InvalidToken("Token user no longer exists.") from exc
        data = serializer.validated_data
        response = Response({"access": data["access"]}, status=status.HTTP_200_OK)
        set_refresh_cookie(response, data["refresh"])
        return response

    def handle_exception(self, exc):
        response = super().handle_exception(exc)
        clear_refresh_cookie(response)
        return response


class LogoutView(APIView):
    """End the session held in the refresh cookie."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(
        request=None,
        parameters=[AUTH_HEADER_PARAMETER, REFRESH_COOKIE_PARAMETER],
        responses={204: None, 403: COOKIE_CSRF_403},
        description="Blacklists the refresh cookie's token (if any) and clears the cookie.",
    )
    def post(self, request, *args, **kwargs):
        check_cookie_request(request)
        token = read_refresh_cookie(request)
        if token:
            # An invalid or already blacklisted token has nothing left to revoke.
            with contextlib.suppress(TokenError):
                RefreshToken(token).blacklist()
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response


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
