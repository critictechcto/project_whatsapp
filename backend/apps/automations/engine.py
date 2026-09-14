"""Evaluate automation rules for one inbound message and run their actions.

Flow (``process_inbound``):

1. Only stored inbound customer messages are processed; reactions and unsupported messages are
   ignored. Outbound messages (inbox, campaign, automation, API) never reach the engine, so an
   automation reply can't trigger another automation.
2. Active rules for the workspace whose ``phone_number`` is null or the conversation's number are
   evaluated by ``priority`` then ``created_at``.
3. The conversation row is locked for the whole evaluation, which serialises processing per
   conversation so cooldowns, the hourly cap and the run log stay exact.
4. A rule that already has a run for this message is not executed again (redelivery is a no-op).
   Otherwise its guards run (plan feature for keyword rules, cooldown, hourly send cap); a guard
   records a ``skipped`` run. Then its actions run in order.
5. ``stop_processing`` on a matched rule (whatever its run status) stops lower-priority rules.

Messages claimed by commerce (``common.commerce.is_claimed_by_commerce``: carts, ``upc:`` replies,
store keywords) are never queued by ``receivers.on_message_recorded`` and record nothing; stored
``order`` messages are ignored here as well.

Action failure semantics: each action runs in its own savepoint. Policy errors (409s such as
``outside_service_window``), validation errors and missing referenced objects mark that action
``failed``; they never raise. A failed *send* halts the remaining actions (recorded ``not_run``) so
a sequence never continues without its message, e.g. a conversation is not closed when the reply
could not be queued. Other failed actions don't halt. A run with any failed action is ``failed``.

Commerce send actions (``send_shop_menu``, ``send_catalog``, ``send_collection``) run the handler
``apps.shop`` registers in :mod:`.hooks`. Without one, or when the handler raises
``ActionSkipped``, the action is ``skipped`` ("Store is not available.") and, being a send, halts
later actions. A run whose actions were only skipped (none succeeded or failed) is ``skipped``.
Unexpected errors (database, bugs) propagate and roll the whole evaluation back so the task can be
retried safely.
"""

import logging
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from rest_framework.exceptions import APIException, ErrorDetail

from apps.billing import entitlements
from apps.contacts import services as contact_services
from apps.contacts.models import Contact, Tag
from apps.inbox import sending
from apps.inbox import services as inbox_services
from apps.inbox.models import Conversation, Message
from apps.message_templates.models import MessageTemplate
from apps.tenants.models import Membership

from . import business_hours, matching
from .hooks import (
    COMMERCE_ACTION_TYPES,
    STORE_UNAVAILABLE,
    ActionFailed,
    ActionSkipped,
    get_commerce_action,
    idempotency_key,
)
from .models import AutomationRule, AutomationRun, BusinessHours

logger = logging.getLogger(__name__)

Trigger = AutomationRule.Trigger
RunStatus = AutomationRun.Status

# At most this many automation messages per conversation in any rolling hour.
MAX_AUTOMATED_SENDS_PER_HOUR = 10
SEND_CAP_WINDOW = timedelta(hours=1)
SEND_ACTIONS = frozenset({"send_text", "send_template", *COMMERCE_ACTION_TYPES})
# Reactions to an automated reply would otherwise trigger more replies; unsupported/system
# messages carry no customer text; native carts (orders) are always answered by commerce.
IGNORED_MESSAGE_TYPES = frozenset(
    {Message.Type.REACTION, Message.Type.UNSUPPORTED, Message.Type.ORDER}
)
# Contact fields a VariableSource with ``source == "contact_field"`` may read.
CONTACT_FIELDS = ("name", "phone_e164", "email")
DETAIL_MAX_LENGTH = 1000

ACTION_SUCCEEDED, ACTION_FAILED, ACTION_NOT_RUN = "succeeded", "failed", "not_run"
ACTION_SKIPPED = "skipped"
STORE_UNAVAILABLE_CODE = "store_unavailable"

__all__ = ("ActionFailed", "ActionSkipped", "idempotency_key", "process_inbound")


@dataclass(frozen=True, slots=True)
class InboundContext:
    text: str
    is_first_inbound: bool
    contact_created: bool
    occurred_at: datetime


# --- Entry point --------------------------------------------------------------------------------


def process_inbound(
    message_id,
    *,
    is_first_inbound: bool | None = None,
    contact_created: bool | None = None,
) -> list[AutomationRun]:
    """Run matching rules for an inbound message. Returns the runs for matched rules (existing
    runs included when the message is reprocessed).

    ``is_first_inbound``/``contact_created`` come from the ``MessageRecorded`` event. When
    omitted, the first flag is derived from stored messages and the second is taken as false.
    """
    message = Message.objects.select_related("workspace").filter(pk=message_id).first()
    if message is None:
        logger.info("Automation skipped: message %s no longer exists", message_id)
        return []
    if (
        message.direction != Message.Direction.INBOUND
        or message.source != Message.Source.INBOUND
        or message.type in IGNORED_MESSAGE_TYPES
        or not message.workspace.is_active
    ):
        return []

    with transaction.atomic():
        conversation = (
            Conversation.objects.select_for_update(of=("self",))
            .select_related("contact", "phone_number__waba")
            .get(pk=message.conversation_id)
        )
        rules = list(
            AutomationRule.objects.filter(workspace_id=message.workspace_id, is_active=True)
            .filter(Q(phone_number__isnull=True) | Q(phone_number_id=conversation.phone_number_id))
            .order_by("priority", "created_at")
        )
        if not rules:
            return []
        if is_first_inbound is None:
            is_first_inbound = not Message.objects.filter(
                conversation_id=conversation.pk,
                direction=Message.Direction.INBOUND,
                created_at__lt=message.created_at,
            ).exists()
        context = InboundContext(
            text=message.text,
            is_first_inbound=bool(is_first_inbound),
            contact_created=bool(contact_created),
            occurred_at=message.sent_at or message.created_at,
        )
        triggers = TriggerEvaluator(message.workspace, context)
        existing = {run.rule_id: run for run in AutomationRun.objects.filter(message=message)}

        runs: list[AutomationRun] = []
        for rule in rules:
            run = existing.get(rule.pk)
            if run is None:
                if not triggers.matches(rule):
                    continue
                run = execute_rule(rule, message, conversation)
            runs.append(run)
            if rule.stop_processing:
                break
    return runs


# --- Triggers -----------------------------------------------------------------------------------


class TriggerEvaluator:
    """Evaluates rule triggers for one message; business hours are loaded at most once."""

    def __init__(self, workspace, context: InboundContext) -> None:
        self.workspace = workspace
        self.context = context
        self._outside_hours: bool | None = None

    def matches(self, rule: AutomationRule) -> bool:
        if rule.trigger == Trigger.KEYWORD:
            return matching.keyword_matches(self.context.text, rule.keywords, rule.keyword_match)
        if rule.trigger == Trigger.FIRST_INBOUND:
            return self.context.is_first_inbound
        if rule.trigger == Trigger.NEW_CONTACT:
            return self.context.contact_created
        if rule.trigger == Trigger.OUTSIDE_BUSINESS_HOURS:
            return self.outside_business_hours()
        return False

    def outside_business_hours(self) -> bool:
        if self._outside_hours is None:
            hours = BusinessHours.objects.filter(workspace=self.workspace).first()
            self._outside_hours = hours is not None and business_hours.is_outside(
                enabled=hours.enabled,
                schedule=hours.schedule,
                moment=self.context.occurred_at,
                time_zone=self.workspace.time_zone,
            )
        return self._outside_hours


# --- Rule execution -----------------------------------------------------------------------------


def execute_rule(
    rule: AutomationRule, message: Message, conversation: Conversation
) -> AutomationRun:
    now = timezone.now()
    reason = skip_reason(rule, message, conversation, now)
    if reason:
        return _record(rule, message, conversation, RunStatus.SKIPPED, reason, [])

    results = run_actions(rule, message, conversation)
    statuses = {result["status"] for result in results}
    if ACTION_FAILED in statuses:
        status = RunStatus.FAILED
    elif ACTION_SKIPPED in statuses and ACTION_SUCCEEDED not in statuses:
        status = RunStatus.SKIPPED  # nothing ran, e.g. the store is not available
    else:
        status = RunStatus.SUCCEEDED
    run = _record(rule, message, conversation, status, summarize(results), results)
    if status != RunStatus.SKIPPED:
        AutomationRule.objects.filter(pk=rule.pk).update(
            run_count=F("run_count") + 1, last_triggered_at=now
        )
    return run


def skip_reason(
    rule: AutomationRule, message: Message, conversation: Conversation, now: datetime
) -> str:
    """Why a matched rule must not run now ("" when it may)."""
    if rule.trigger == Trigger.KEYWORD and not entitlements.has_feature(
        message.workspace, entitlements.KEYWORD_AUTOMATIONS
    ):
        return "Keyword automations are not included in this workspace's plan."

    if rule.cooldown_minutes:
        ran_recently = AutomationRun.objects.filter(
            rule=rule,
            conversation=conversation,
            status__in=(RunStatus.SUCCEEDED, RunStatus.FAILED),
            created_at__gte=now - timedelta(minutes=rule.cooldown_minutes),
        ).exists()
        if ran_recently:
            return (
                f"Cooldown: this rule already ran for this conversation in the last "
                f"{rule.cooldown_minutes} minute(s)."
            )

    sends = sum(1 for action in rule.actions or () if action.get("type") in SEND_ACTIONS)
    if sends:
        recent = Message.objects.filter(
            conversation=conversation,
            direction=Message.Direction.OUTBOUND,
            source=Message.Source.AUTOMATION,
            created_at__gte=now - SEND_CAP_WINDOW,
        ).count()
        if recent + sends > MAX_AUTOMATED_SENDS_PER_HOUR:
            return (
                f"Hourly limit: {recent} automated message(s) were already sent in this "
                f"conversation in the last hour (limit {MAX_AUTOMATED_SENDS_PER_HOUR})."
            )
    return ""


def _record(
    rule: AutomationRule,
    message: Message,
    conversation: Conversation,
    status: str,
    detail: str,
    results: list[dict[str, Any]],
) -> AutomationRun:
    return AutomationRun.objects.create(
        workspace_id=rule.workspace_id,
        rule=rule,
        conversation=conversation,
        message=message,
        status=status,
        detail=detail[:DETAIL_MAX_LENGTH],
        action_results=results,
    )


# --- Actions ------------------------------------------------------------------------------------


def run_actions(
    rule: AutomationRule, message: Message, conversation: Conversation
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    halted = False
    for index, action in enumerate(rule.actions or ()):
        action_type = action.get("type") if isinstance(action, Mapping) else None
        config = action.get("config") if isinstance(action, Mapping) else None
        result: dict[str, Any] = {"index": index, "type": action_type}
        if halted:
            results.append({**result, "status": ACTION_NOT_RUN})
            continue
        try:
            handler = _handler_for(action_type)
            with transaction.atomic():
                outcome = handler(
                    rule=rule,
                    message=message,
                    conversation=conversation,
                    config=config if isinstance(config, Mapping) else {},
                    index=index,
                )
        except ActionSkipped as exc:
            result.update(status=ACTION_SKIPPED, code=exc.code, message=exc.message)
        except ActionFailed as exc:
            result.update(status=ACTION_FAILED, code=exc.code, message=exc.message)
        except APIException as exc:
            code, text = _api_error(exc)
            result.update(status=ACTION_FAILED, code=code, message=text)
        except (ValueError, DjangoValidationError, ObjectDoesNotExist) as exc:
            result.update(status=ACTION_FAILED, code="invalid_action", message=str(exc))
        else:
            result.update(status=ACTION_SUCCEEDED, **outcome)
        if result["status"] == ACTION_FAILED:
            logger.info(
                "Automation rule %s action %s (%s) failed for message %s: %s",
                rule.pk,
                index,
                action_type,
                message.pk,
                result["code"],
            )
            halted = action_type in SEND_ACTIONS
        elif result["status"] == ACTION_SKIPPED:
            # A skipped send halts too: later actions must not run without their message.
            halted = action_type in SEND_ACTIONS
        results.append(result)
    return results


def _handler_for(action_type: Any) -> "ActionHandler":
    if action_type in COMMERCE_ACTION_TYPES:
        return get_commerce_action(action_type) or _store_unavailable
    handler = ACTION_HANDLERS.get(action_type)
    if handler is None:
        raise ActionFailed("unknown_action", f"Unknown action type {action_type!r}.")
    return handler


def summarize(results: list[dict[str, Any]]) -> str:
    failed = [result for result in results if result["status"] == ACTION_FAILED]
    skipped = [result for result in results if result["status"] == ACTION_SKIPPED]
    succeeded = any(result["status"] == ACTION_SUCCEEDED for result in results)
    if not failed and not skipped:
        return f"Ran {len(results)} action(s)."
    if not failed and not succeeded and len({result["message"] for result in skipped}) == 1:
        detail = skipped[0]["message"]  # e.g. "Store is not available."
    else:
        parts = [
            f"action {result['index'] + 1} ({result['type']}): {result['code']}: "
            f"{result['message']}"
            for result in failed + skipped
        ]
        counts = []
        if failed:
            counts.append(f"{len(failed)} of {len(results)} action(s) failed")
        if skipped:
            counts.append(f"{len(skipped)} of {len(results)} action(s) skipped")
        detail = f"{' and '.join(counts)}. " + "; ".join(parts)
    not_run = sum(1 for result in results if result["status"] == ACTION_NOT_RUN)
    if not_run:
        detail = detail.rstrip(".")
        detail += f". {not_run} later action(s) not run because a message could not be sent."
    return detail


def _api_error(exc: APIException) -> tuple[str, str]:
    detail = exc.detail
    if isinstance(detail, ErrorDetail):
        return detail.code or "error", str(detail)
    return "invalid", _flatten(detail)


def _flatten(detail: Any) -> str:
    if isinstance(detail, Mapping):
        return "; ".join(f"{key}: {_flatten(value)}" for key, value in detail.items())
    if isinstance(detail, list | tuple):
        return " ".join(_flatten(item) for item in detail)
    return str(detail)


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def resolve_variable(contact: Contact, source: Mapping[str, Any]) -> str:
    """Value of a ``VariableSource`` for ``contact``; blank values use the fallback."""
    kind = source.get("source")
    key = str(source.get("value") or "")
    value: Any = ""
    if kind == "static":
        value = key
    elif kind == "contact_field" and key in CONTACT_FIELDS:
        value = getattr(contact, key, "")
    elif kind == "attribute":
        value = (contact.attributes or {}).get(key) if isinstance(contact.attributes, dict) else ""
    text = "" if value is None else str(value).strip()
    return text or str(source.get("fallback") or "").strip()


ActionHandler = Callable[..., dict[str, Any]]


def _send_text(*, rule, message, conversation, config, index) -> dict[str, Any]:
    if not sending.window_open(conversation.contact, conversation.phone_number):
        raise sending.OutsideServiceWindow()
    sent = sending.send_message(
        workspace=message.workspace,
        contact=conversation.contact,
        content=sending.TextContent(str(config.get("text") or "")),
        conversation=conversation,
        source=Message.Source.AUTOMATION,
        source_ref=str(rule.pk),
        idempotency_key=idempotency_key(rule, message, index),
    )
    return {"message_id": str(sent.pk)}


def _send_template(*, rule, message, conversation, config, index) -> dict[str, Any]:
    template_id = _uuid(config.get("template_id"))
    template = (
        MessageTemplate.objects.filter(workspace_id=message.workspace_id, pk=template_id).first()
        if template_id
        else None
    )
    if template is None:
        raise ActionFailed("template_not_found", "The template no longer exists.")
    params = []
    for position, source in enumerate(config.get("body_params") or (), start=1):
        value = resolve_variable(
            conversation.contact, source if isinstance(source, Mapping) else {}
        )
        if not value:
            raise ActionFailed(
                "missing_variable",
                f"Body variable {{{{{position}}}}} has no value for this contact and no fallback.",
            )
        params.append(value)
    sent = sending.send_message(
        workspace=message.workspace,
        contact=conversation.contact,
        content=sending.TemplateContent(template, body_params=params),
        conversation=conversation,
        source=Message.Source.AUTOMATION,
        source_ref=str(rule.pk),
        idempotency_key=idempotency_key(rule, message, index),
    )
    return {"message_id": str(sent.pk)}


def _add_tags(*, rule, message, conversation, config, index) -> dict[str, Any]:
    ids = [tag_id for tag_id in map(_uuid, config.get("tag_ids") or ()) if tag_id]
    tags = list(Tag.objects.filter(workspace_id=message.workspace_id, pk__in=ids))
    if not tags:
        raise ActionFailed("tags_not_found", "None of the tags exist any more.")
    contact_services.add_tags(conversation.contact, tags)
    return {"tag_ids": sorted(str(tag.pk) for tag in tags)}


def _assign(*, rule, message, conversation, config, index) -> dict[str, Any]:
    user_id = _uuid(config.get("user_id"))
    membership = (
        Membership.objects.select_related("user")
        .filter(workspace_id=message.workspace_id, user_id=user_id)
        .first()
        if user_id
        else None
    )
    if membership is None:
        raise ActionFailed(
            "assignee_not_member", "The assignee is no longer a member of this workspace."
        )
    inbox_services.assign(conversation, membership.user, actor=None)
    return {}


def _close_conversation(*, rule, message, conversation, config, index) -> dict[str, Any]:
    inbox_services.close(conversation, actor=None)
    return {}


def _store_unavailable(*, rule, message, conversation, config, index) -> dict[str, Any]:
    """Commerce actions without a registered handler (the shop app is not installed)."""
    raise ActionSkipped(STORE_UNAVAILABLE_CODE, STORE_UNAVAILABLE)


ACTION_HANDLERS: dict[str, ActionHandler] = {
    "send_text": _send_text,
    "send_template": _send_template,
    "add_tags": _add_tags,
    "assign": _assign,
    "close_conversation": _close_conversation,
}
