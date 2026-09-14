import pytest

from apps.message_templates.factories import MessageTemplateFactory
from apps.message_templates.models import MessageTemplate
from common.events import (
    TemplateCategoryUpdate,
    TemplateQualityUpdate,
    TemplateStatusUpdate,
    emit,
    template_category_updated,
    template_quality_updated,
    template_status_updated,
)

pytestmark = pytest.mark.django_db

Status = MessageTemplate.Status


@pytest.fixture
def template(waba):
    return MessageTemplateFactory(
        waba=waba, meta_template_id="123456789", status=Status.PENDING, category="UTILITY"
    )


def status_event(template, event, *, reason=None, workspace_id=None, meta_id=None):
    return TemplateStatusUpdate(
        workspace_id=workspace_id or template.workspace_id,
        waba_id=template.waba.waba_id,
        meta_template_id=meta_id or template.meta_template_id,
        name=template.name,
        language=template.language,
        event=event,
        reason=reason,
    )


def test_status_update_approves(template):
    failures = emit(template_status_updated, status_event(template, "APPROVED", reason="NONE"))

    assert failures == []
    template.refresh_from_db()
    assert template.status == Status.APPROVED
    assert template.rejected_reason == ""


def test_status_update_rejection_is_idempotent(template):
    event = status_event(template, "REJECTED", reason="INCORRECT_CATEGORY")

    emit(template_status_updated, event)
    emit(template_status_updated, event)

    template.refresh_from_db()
    assert template.status == Status.REJECTED
    assert template.rejected_reason == "INCORRECT_CATEGORY"


def test_reinstated_means_approved_and_flagged_keeps_status(template):
    emit(template_status_updated, status_event(template, "FLAGGED"))
    template.refresh_from_db()
    assert template.status == Status.PENDING

    emit(template_status_updated, status_event(template, "REINSTATED"))
    template.refresh_from_db()
    assert template.status == Status.APPROVED


def test_status_update_from_other_workspace_is_ignored(template, other_workspace, fake_graph):
    emit(
        template_status_updated,
        status_event(template, "APPROVED", workspace_id=other_workspace.pk),
    )

    template.refresh_from_db()
    assert template.status == Status.PENDING
    assert fake_graph.calls_to("list_templates") == []


def test_unknown_template_triggers_sync(template, waba, fake_graph):
    fake_graph.add_template(waba.waba_id, id="999", name="new_offer", status="APPROVED")
    fake_graph.add_template(waba.waba_id, id=template.meta_template_id, name=template.name)

    failures = emit(template_status_updated, status_event(template, "APPROVED", meta_id="999"))

    assert failures == []
    assert len(fake_graph.calls_to("list_templates")) == 1
    synced = MessageTemplate.objects.get(meta_template_id="999")
    assert synced.workspace == waba.workspace
    assert synced.status == Status.APPROVED


def test_category_update(template):
    event = TemplateCategoryUpdate(
        workspace_id=template.workspace_id,
        waba_id=template.waba.waba_id,
        meta_template_id=template.meta_template_id,
        name=template.name,
        language=template.language,
        previous_category="UTILITY",
        new_category="MARKETING",
    )

    emit(template_category_updated, event)
    emit(template_category_updated, event)

    template.refresh_from_db()
    assert template.category == "MARKETING"
    assert template.previous_category == "UTILITY"


def test_quality_update(template, other_workspace):
    fields = {
        "waba_id": template.waba.waba_id,
        "meta_template_id": template.meta_template_id,
        "name": template.name,
        "language": template.language,
        "previous_quality_score": "GREEN",
        "new_quality_score": "RED",
    }

    emit(template_quality_updated, TemplateQualityUpdate(workspace_id=other_workspace.pk, **fields))
    template.refresh_from_db()
    assert template.quality_score == "UNKNOWN"

    emit(
        template_quality_updated,
        TemplateQualityUpdate(workspace_id=template.workspace_id, **fields),
    )
    template.refresh_from_db()
    assert template.quality_score == "RED"
