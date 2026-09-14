"""Start the free trial when a workspace is created. Idempotent: the subscription is keyed on the
workspace, and ``services.get_subscription`` still creates the trial lazily if this didn't run."""

from django.dispatch import receiver

from apps.tenants.models import Workspace
from common.events import WorkspaceCreated, workspace_created

from . import services


@receiver(workspace_created, dispatch_uid="billing.start_trial_on_workspace_created")
def start_trial_on_workspace_created(sender, event: WorkspaceCreated, **kwargs) -> None:
    workspace = Workspace.objects.filter(pk=event.workspace_id).first()
    if workspace is None:
        return
    services.get_subscription(workspace)
