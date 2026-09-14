"""The generated schema carries the wave-2 contract names (docs/contracts/wave-2.md).

Frontend types are generated from these component names, enum names and operation ids, so
renaming a serializer or an ``operation_id`` must be a deliberate contract change.
"""

import pytest
from drf_spectacular.generators import SchemaGenerator

from apps.automations import schema_enums as automation_enums
from apps.billing import schema_enums as billing_enums
from apps.campaigns import schema_enums as campaign_enums
from apps.inbox import schema_enums as inbox_enums

CONTRACT_COMPONENTS = {
    # inbox
    "AssignConversationRequest",
    "Conversation",
    "ConversationContact",
    "ConversationNote",
    "ConversationNoteRequest",
    "ConversationPhoneNumber",
    "MediaAsset",
    "MediaUploadRequest",
    "Message",
    "MessageMedia",
    "MessagePreview",
    "MessageTemplateRef",
    "PaginatedConversationList",
    "PaginatedConversationNoteList",
    "PaginatedMessageList",
    "SendMessageRequest",
    "StartConversationRequest",
    "UserSummary",
    "WsTicket",
    # campaigns
    "AudiencePreview",
    "AudienceSkipped",
    "Campaign",
    "CampaignAudience",
    "CampaignAudienceRequest",
    "CampaignRecipient",
    "CampaignStats",
    "CampaignTemplate",
    "CampaignWriteRequest",
    "CostEstimate",
    "LaunchCampaignRequest",
    "PaginatedCampaignList",
    "PaginatedCampaignRecipientList",
    "PatchedCampaignWriteRequest",
    "VariableMapping",
    "VariableMappingRequest",
    "VariableSource",
    "VariableSourceRequest",
    # automations
    "AutomationAction",
    "AutomationActionRequest",
    "AutomationRule",
    "AutomationRuleRef",
    "AutomationRuleRequest",
    "AutomationRun",
    "BusinessHours",
    "BusinessHoursSlot",
    "BusinessHoursSlotRequest",
    "PaginatedAutomationRuleList",
    "PaginatedAutomationRunList",
    "PatchedAutomationRuleRequest",
    "PatchedBusinessHoursRequest",
    # billing
    "BillingProfile",
    "CancelSubscriptionRequest",
    "CheckoutPrefill",
    "CheckoutRequest",
    "CheckoutSession",
    "CheckoutVerifyRequest",
    "Invoice",
    "PaginatedInvoiceList",
    "PatchedBillingProfileRequest",
    "Plan",
    "PlanLimits",
    "Subscription",
    "Usage",
    "UsageMetric",
    # enums reused from earlier waves
    "ContactOptInStatusEnum",
    "MessageTemplateCategoryEnum",
}

CONTRACT_ENUMS = {
    name: values
    for module in (inbox_enums, campaign_enums, automation_enums, billing_enums)
    for name, values in module.ENUM_NAME_OVERRIDES.items()
}

CONTRACT_OPERATIONS = {
    ("post", "/api/v1/inbox/ws-ticket/"): "inbox_ws_ticket_create",
    ("get", "/api/v1/inbox/conversations/"): "inbox_conversations_list",
    ("post", "/api/v1/inbox/conversations/"): "inbox_conversations_create",
    ("get", "/api/v1/inbox/conversations/{id}/"): "inbox_conversations_retrieve",
    ("post", "/api/v1/inbox/conversations/{id}/assign/"): "inbox_conversations_assign_create",
    ("post", "/api/v1/inbox/conversations/{id}/close/"): "inbox_conversations_close_create",
    ("post", "/api/v1/inbox/conversations/{id}/reopen/"): "inbox_conversations_reopen_create",
    ("post", "/api/v1/inbox/conversations/{id}/read/"): "inbox_conversations_read_create",
    ("get", "/api/v1/inbox/conversations/{id}/messages/"): "inbox_conversations_messages_list",
    ("post", "/api/v1/inbox/conversations/{id}/messages/"): "inbox_conversations_messages_create",
    ("get", "/api/v1/inbox/conversations/{id}/notes/"): "inbox_conversations_notes_list",
    ("post", "/api/v1/inbox/conversations/{id}/notes/"): "inbox_conversations_notes_create",
    ("post", "/api/v1/inbox/media/"): "inbox_media_create",
    ("get", "/api/v1/inbox/messages/{id}/media/"): "inbox_messages_media_retrieve",
    ("get", "/api/v1/campaigns/"): "campaigns_list",
    ("post", "/api/v1/campaigns/"): "campaigns_create",
    ("get", "/api/v1/campaigns/{id}/"): "campaigns_retrieve",
    ("patch", "/api/v1/campaigns/{id}/"): "campaigns_partial_update",
    ("delete", "/api/v1/campaigns/{id}/"): "campaigns_destroy",
    ("post", "/api/v1/campaigns/{id}/audience-preview/"): "campaigns_audience_preview_create",
    ("post", "/api/v1/campaigns/{id}/launch/"): "campaigns_launch_create",
    ("post", "/api/v1/campaigns/{id}/pause/"): "campaigns_pause_create",
    ("post", "/api/v1/campaigns/{id}/resume/"): "campaigns_resume_create",
    ("post", "/api/v1/campaigns/{id}/cancel/"): "campaigns_cancel_create",
    ("get", "/api/v1/campaigns/{id}/recipients/"): "campaigns_recipients_list",
    ("get", "/api/v1/automations/rules/"): "automations_rules_list",
    ("post", "/api/v1/automations/rules/"): "automations_rules_create",
    ("get", "/api/v1/automations/rules/{id}/"): "automations_rules_retrieve",
    ("patch", "/api/v1/automations/rules/{id}/"): "automations_rules_partial_update",
    ("delete", "/api/v1/automations/rules/{id}/"): "automations_rules_destroy",
    ("get", "/api/v1/automations/business-hours/"): "automations_business_hours_retrieve",
    ("patch", "/api/v1/automations/business-hours/"): "automations_business_hours_partial_update",
    ("get", "/api/v1/automations/runs/"): "automations_runs_list",
    ("get", "/api/v1/billing/plans/"): "billing_plans_list",
    ("get", "/api/v1/billing/subscription/"): "billing_subscription_retrieve",
    ("post", "/api/v1/billing/subscription/checkout/"): "billing_subscription_checkout_create",
    ("post", "/api/v1/billing/subscription/verify/"): "billing_subscription_verify_create",
    ("post", "/api/v1/billing/subscription/cancel/"): "billing_subscription_cancel_create",
    ("get", "/api/v1/billing/billing-profile/"): "billing_profile_retrieve",
    ("patch", "/api/v1/billing/billing-profile/"): "billing_profile_partial_update",
    ("get", "/api/v1/billing/invoices/"): "billing_invoices_list",
    ("get", "/api/v1/billing/usage/"): "billing_usage_retrieve",
}


@pytest.fixture(scope="module")
def schema():
    return SchemaGenerator().get_schema(request=None, public=True)


def test_contract_components_exist(schema):
    missing = CONTRACT_COMPONENTS - set(schema["components"]["schemas"])

    assert not missing


@pytest.mark.parametrize("name", sorted(CONTRACT_ENUMS))
def test_contract_enums_have_contract_values(schema, name):
    component = schema["components"]["schemas"].get(name)

    assert component is not None, f"{name} missing from the schema"
    assert component["enum"] == list(CONTRACT_ENUMS[name])


def test_contract_operation_ids(schema):
    actual = {
        (method, route): operation["operationId"]
        for route, item in schema["paths"].items()
        for method, operation in item.items()
        if isinstance(operation, dict) and "operationId" in operation
    }

    mismatched = {
        key: (expected, actual.get(key))
        for key, expected in CONTRACT_OPERATIONS.items()
        if actual.get(key) != expected
    }
    assert not mismatched


def test_operation_ids_are_unique(schema):
    operation_ids = [
        operation["operationId"]
        for item in schema["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]

    assert len(operation_ids) == len(set(operation_ids))


def _operation(schema, method, route):
    return schema["paths"][route][method]


def test_send_message_documents_idempotency_key(schema):
    operation = _operation(schema, "post", "/api/v1/inbox/conversations/{id}/messages/")

    assert any(
        parameter["name"] == "Idempotency-Key" and parameter["in"] == "header"
        for parameter in operation["parameters"]
    )
    assert set(operation["responses"]) >= {"201"}


def test_media_upload_is_multipart(schema):
    operation = _operation(schema, "post", "/api/v1/inbox/media/")

    assert list(operation["requestBody"]["content"]) == ["multipart/form-data"]


def test_list_endpoints_are_paginated_except_plans(schema):
    conversations = _operation(schema, "get", "/api/v1/inbox/conversations/")
    plans = _operation(schema, "get", "/api/v1/billing/plans/")

    ok = conversations["responses"]["200"]["content"]["application/json"]["schema"]
    assert ok == {"$ref": "#/components/schemas/PaginatedConversationList"}
    parameter_names = {parameter["name"] for parameter in conversations["parameters"]}
    assert {"cursor", "page_size", "status", "assignee", "search"} <= parameter_names
    plan_schema = plans["responses"]["200"]["content"]["application/json"]["schema"]
    assert plan_schema["type"] == "array"


def test_razorpay_webhook_is_not_documented(schema):
    assert not any(route.startswith("/webhooks/") for route in schema["paths"])
