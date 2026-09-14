import uuid

from django.db import models


class UUIDTimeStampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ("-created_at",)
        get_latest_by = "created_at"


class TenantScopedQuerySet(models.QuerySet):
    def for_workspace(self, workspace):
        return self.filter(workspace=workspace)


class TenantScopedModel(UUIDTimeStampedModel):
    """Base for every row owned by a workspace. Always filter by workspace in views/services."""

    workspace = models.ForeignKey(
        "tenants.Workspace",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    objects = TenantScopedQuerySet.as_manager()

    class Meta(UUIDTimeStampedModel.Meta):
        abstract = True
