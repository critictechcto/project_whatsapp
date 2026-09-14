"""React to template webhooks (parsed by the webhooks app). All handlers are idempotent."""

import logging

from django.dispatch import receiver

from apps.whatsapp.models import WhatsAppBusinessAccount
from common.events import (
    TemplateCategoryUpdate,
    TemplateQualityUpdate,
    TemplateStatusUpdate,
    template_category_updated,
    template_quality_updated,
    template_status_updated,
)

from .models import MessageTemplate
from .services import normalize_reason
from .tasks import sync_waba

logger = logging.getLogger(__name__)

Status = MessageTemplate.Status

# Webhook events that are not statuses themselves.
_EVENT_STATUS = {"REINSTATED": Status.APPROVED}
_IGNORED_EVENTS = {"FLAGGED"}  # quality warning; the status stays as it is


def _find(event) -> MessageTemplate | None:
    return MessageTemplate.objects.filter(
        workspace_id=event.workspace_id, meta_template_id=str(event.meta_template_id)
    ).first()


@receiver(template_status_updated, dispatch_uid="message_templates.status_updated")
def on_template_status_updated(sender, event: TemplateStatusUpdate, **kwargs) -> None:
    template = _find(event)
    if template is None:
        waba = WhatsAppBusinessAccount.objects.filter(
            waba_id=event.waba_id, workspace_id=event.workspace_id
        ).first()
        if waba is not None:
            sync_waba.delay(str(waba.pk))
        return

    event_name = str(event.event or "").upper()
    if event_name in _IGNORED_EVENTS:
        return
    status = _EVENT_STATUS.get(event_name, event_name)
    if status not in Status.values:
        logger.info("Ignoring unknown template event %s for %s", event_name, template.pk)
        return
    reason = normalize_reason(event.reason)
    if template.status == status and template.rejected_reason == reason:
        return
    template.status = status
    template.rejected_reason = reason
    template.save(update_fields=["status", "rejected_reason", "updated_at"])


@receiver(template_category_updated, dispatch_uid="message_templates.category_updated")
def on_template_category_updated(sender, event: TemplateCategoryUpdate, **kwargs) -> None:
    template = _find(event)
    if template is None:
        return
    category = str(event.new_category or "").upper()
    previous = str(event.previous_category or "").upper()
    if not category or (template.category == category and template.previous_category == previous):
        return
    template.previous_category = previous
    template.category = category
    template.save(update_fields=["previous_category", "category", "updated_at"])


@receiver(template_quality_updated, dispatch_uid="message_templates.quality_updated")
def on_template_quality_updated(sender, event: TemplateQualityUpdate, **kwargs) -> None:
    template = _find(event)
    if template is None:
        return
    score = str(event.new_quality_score or "").upper()
    if score not in MessageTemplate.QualityScore.values:
        score = MessageTemplate.QualityScore.UNKNOWN
    if template.quality_score == score:
        return
    template.quality_score = score
    template.save(update_fields=["quality_score", "updated_at"])
