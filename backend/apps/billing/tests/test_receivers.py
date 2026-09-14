"""WorkspaceCreated starts the Growth trial; get_subscription stays the lazy fallback."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.billing.models import Subscription
from apps.billing.plans import TRIAL_PLAN_SLUG
from apps.tenants import services as tenant_services
from common import events

pytestmark = pytest.mark.django_db


def test_new_workspace_starts_a_14_day_growth_trial(user, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        workspace = tenant_services.create_workspace(user=user, name="Sharma Retail")

    subscription = Subscription.objects.get(workspace=workspace)
    assert (subscription.status, subscription.plan_id) == ("trialing", TRIAL_PLAN_SLUG)
    remaining = subscription.trial_ends_at - timezone.now()
    assert timedelta(days=13, hours=23) < remaining <= timedelta(days=14)


def test_trial_waits_for_commit(user, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=False):
        workspace = tenant_services.create_workspace(user=user, name="Sharma Retail")

    assert not Subscription.objects.filter(workspace=workspace).exists()


def test_receiver_is_idempotent_and_ignores_missing_workspaces(workspace):
    event = events.WorkspaceCreated(workspace_id=workspace.pk, owner_id=workspace.created_by_id)

    assert events.emit(events.workspace_created, event) == []
    assert events.emit(events.workspace_created, event) == []
    missing = events.WorkspaceCreated(workspace_id=uuid.uuid4(), owner_id=uuid.uuid4())
    assert events.emit(events.workspace_created, missing) == []

    assert Subscription.objects.filter(workspace=workspace).count() == 1
