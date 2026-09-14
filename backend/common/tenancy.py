"""Workspace (tenant) resolution and role-based permissions for API views.

Tenant-owned endpoints read the active workspace from the ``X-Workspace-ID`` header. Views use
:class:`WorkspaceScopedMixin` (or the ready-made viewsets below), which resolves the caller's
membership, enforces a minimum role per action, filters the queryset to the workspace and sets
the workspace on created objects. Non-members get 404 so workspace ids don't leak.
"""

import uuid

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from rest_framework import exceptions, generics, mixins, viewsets
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated

from common.roles import Role, role_at_least

WORKSPACE_HEADER = "X-Workspace-ID"


class WorkspaceRequired(exceptions.APIException):
    status_code = 400
    default_code = "workspace_required"
    default_detail = f"Send the {WORKSPACE_HEADER} header with a workspace id."


class WorkspaceNotFound(exceptions.NotFound):
    default_code = "workspace_not_found"
    default_detail = "Workspace not found."


class InsufficientRole(exceptions.PermissionDenied):
    default_code = "insufficient_role"
    default_detail = "Your role in this workspace does not allow this action."


def get_request_membership(request):
    """Return the caller's Membership for the header workspace, cached on the request.

    Also sets ``request.workspace`` and ``request.membership``.
    """
    cached = getattr(request, "_workspace_membership", None)
    if cached is not None:
        return cached

    raw = request.headers.get(WORKSPACE_HEADER, "").strip()
    if not raw:
        raise WorkspaceRequired()
    try:
        workspace_id = uuid.UUID(raw)
    except ValueError:
        raise WorkspaceNotFound() from None

    user = request.user
    if not user or not user.is_authenticated:
        raise exceptions.NotAuthenticated()

    membership_model = apps.get_model("tenants", "Membership")
    membership = (
        membership_model.objects.select_related("workspace")
        .filter(workspace_id=workspace_id, user=user, workspace__is_active=True)
        .first()
    )
    if membership is None:
        raise WorkspaceNotFound()

    request._workspace_membership = membership
    request.membership = membership
    request.workspace = membership.workspace
    return membership


class IsWorkspaceMember(BasePermission):
    """Caller belongs to the header workspace with at least the role the view requires.

    The required role comes from ``view.get_required_role()`` when defined, otherwise
    ``minimum_role``.
    """

    minimum_role = Role.VIEWER

    def has_permission(self, request, view) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        membership = get_request_membership(request)
        required = self.get_required_role(request, view)
        if not role_at_least(membership.role, required):
            raise InsufficientRole(
                f"This action requires the {Role(required).label.lower()} role or higher."
            )
        return True

    def get_required_role(self, request, view) -> str:
        getter = getattr(view, "get_required_role", None)
        return getter() if getter else self.minimum_role


def HasRole(minimum: str) -> type[BasePermission]:
    """Permission class requiring a fixed minimum role, ignoring the view's role mapping."""

    class _HasRole(IsWorkspaceMember):
        minimum_role = minimum

        def get_required_role(self, request, view) -> str:
            return minimum

    _HasRole.__name__ = f"HasRole{Role(minimum).name.title()}"
    return _HasRole


class WorkspaceScopedMixin:
    """Scope a DRF generic view/viewset to the header workspace.

    - ``read_role`` applies to safe methods, ``write_role`` to the rest.
    - ``action_roles`` overrides per viewset action, e.g. ``{"send": Role.AGENT}``.
    - ``workspace_field`` is the queryset lookup to the workspace. Nested lookups
      (``"waba__workspace"``) filter only; set the workspace yourself when creating.
    """

    workspace_scoped = True
    workspace_field = "workspace"
    read_role: str = Role.VIEWER
    write_role: str = Role.ADMIN
    action_roles: dict[str, str] = {}
    permission_classes = (IsAuthenticated, IsWorkspaceMember)

    def get_required_role(self) -> str:
        action = getattr(self, "action", None)
        if action and action in self.action_roles:
            return self.action_roles[action]
        return self.read_role if self.request.method in SAFE_METHODS else self.write_role

    @property
    def membership(self):
        return get_request_membership(self.request)

    @property
    def workspace(self):
        return self.membership.workspace

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        return queryset.filter(**{self.workspace_field: self.workspace})

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        mro = cls.__mro__
        if mixins.CreateModelMixin in mro and mro.index(mixins.CreateModelMixin) < mro.index(
            WorkspaceScopedMixin
        ):
            # DRF's perform_create would win and objects would be saved without a workspace.
            raise ImproperlyConfigured(
                f"{cls.__name__}: list WorkspaceScopedMixin (or a WorkspaceScoped* base) before "
                "CreateModelMixin."
            )

    def perform_create(self, serializer):
        if "__" in self.workspace_field:
            serializer.save()
        else:
            serializer.save(**{self.workspace_field: self.workspace})

    def get_serializer_context(self):
        context = super().get_serializer_context()
        membership = getattr(self.request, "_workspace_membership", None)
        if membership is not None:
            context["workspace"] = membership.workspace
            context["membership"] = membership
        return context


class WorkspaceScopedViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    pass


class WorkspaceScopedGenericViewSet(WorkspaceScopedMixin, viewsets.GenericViewSet):
    """Compose with DRF mixins (ListModelMixin, ...) for partial CRUD."""


class WorkspaceScopedAPIView(WorkspaceScopedMixin, generics.GenericAPIView):
    pass
