import contextlib
import hashlib
from functools import partial

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle, UserRateThrottle
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
    INVALID_LINK,
    AccessTokenSerializer,
    EmailVerifySerializer,
    MeSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterResponseSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .tasks import send_password_reset_email, send_verification_email
from .tokens import check_password_reset_token, check_verification_token

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
        transaction.on_commit(partial(send_verification_email.delay, str(user.pk)), robust=True)
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


def _blacklist_all_sessions(user) -> None:
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


class UserEmailSendThrottle(UserRateThrottle):
    """``email_send`` per signed-in user."""

    scope = "email_send"


class SubmittedEmailSendThrottle(LoginEmailThrottle):
    """``email_send`` keyed on the submitted email address (sha256 of it, lowercased)."""

    scope = "email_send"
    default_rate = "5/hour"


THROTTLED_429 = OpenApiResponse(description="Too many requests; `throttled` error.")
INVALID_400 = OpenApiResponse(description="Validation error (`invalid`) with field details.")


class EmailVerifyRequestView(APIView):
    """Send (again) the email that confirms the signed-in user's address."""

    throttle_classes = (UserEmailSendThrottle,)

    @extend_schema(
        request=None,
        responses={204: None, 429: THROTTLED_429},
        description=(
            "Emails a new verification link to the signed-in user. Does nothing (still 204) "
            "when the address is already verified."
        ),
    )
    def post(self, request):
        user = request.user
        if user.email_verified_at is None:
            transaction.on_commit(partial(send_verification_email.delay, str(user.pk)), robust=True)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmailVerifyView(AuthThrottleMixin, generics.GenericAPIView):
    """Confirm an email address with the token from the verification link."""

    serializer_class = EmailVerifySerializer
    permission_classes = (AllowAny,)
    authentication_classes = ()

    @extend_schema(
        responses={204: None, 400: INVALID_400, 429: THROTTLED_429},
        description=(
            "Marks the address verified. Idempotent: an already verified address returns 204. "
            f"A bad, expired or outdated token is a 400 on `token`: “{INVALID_LINK}”"
        ),
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        check = check_verification_token(serializer.validated_data["token"])
        if check is None:
            raise exceptions.ValidationError({"token": [INVALID_LINK]})
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=check.user.pk)
            if user.email_verified_at is None:
                if check.expired:
                    raise exceptions.ValidationError({"token": [INVALID_LINK]})
                user.email_verified_at = timezone.now()
                user.save(update_fields=["email_verified_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetRequestView(AuthThrottleMixin, generics.GenericAPIView):
    """Email a password reset link. Always 204, so it never reveals whether an account exists."""

    serializer_class = PasswordResetRequestSerializer
    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = (ScopedRateThrottle, SubmittedEmailSendThrottle)

    @extend_schema(
        responses={204: None, 400: INVALID_400, 429: THROTTLED_429},
        description=(
            "Emails a one-time reset link to an active account with this address. Returns 204 "
            "whether or not the account exists."
        ),
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip()
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user is not None:
            transaction.on_commit(
                partial(send_password_reset_email.delay, str(user.pk)), robust=True
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetConfirmView(AuthThrottleMixin, generics.GenericAPIView):
    """Set a new password with the token from the reset link; signs out every session."""

    serializer_class = PasswordResetConfirmSerializer
    permission_classes = (AllowAny,)
    authentication_classes = ()

    @extend_schema(
        responses={204: None, 400: INVALID_400, 429: THROTTLED_429},
        description=(
            f"A bad, expired or used token is a 400 on `token`: “{INVALID_LINK}” A password "
            "the validators reject is a 400 on `new_password`. On success every session is "
            "signed out and the email counts as verified."
        ),
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            # Lock, then check the token again: two requests racing with one token get one use.
            list(User.objects.select_for_update().filter(pk=serializer.validated_data["user"].pk))
            user = check_password_reset_token(serializer.validated_data["token"])
            if user is None:
                raise exceptions.ValidationError({"token": [INVALID_LINK]})
            user.set_password(serializer.validated_data["new_password"])
            fields = ["password"]
            if user.email_verified_at is None:
                user.email_verified_at = timezone.now()
                fields.append("email_verified_at")
            user.save(update_fields=fields)
            _blacklist_all_sessions(user)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
            _blacklist_all_sessions(user)
        return Response(status=status.HTTP_204_NO_CONTENT)
