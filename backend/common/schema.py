from drf_spectacular.openapi import AutoSchema as SpectacularAutoSchema
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter

from common.tenancy import WORKSPACE_HEADER

WORKSPACE_PARAMETER = OpenApiParameter(
    name=WORKSPACE_HEADER,
    type=OpenApiTypes.UUID,
    location=OpenApiParameter.HEADER,
    required=True,
    description="Workspace to act in. The caller must be a member.",
)


class AutoSchema(SpectacularAutoSchema):
    """Documents the X-Workspace-ID header on every workspace-scoped view."""

    def get_override_parameters(self):
        parameters = super().get_override_parameters()
        if getattr(self.view, "workspace_scoped", False):
            parameters = [WORKSPACE_PARAMETER, *parameters]
        return parameters
