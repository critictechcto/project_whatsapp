import pytest
from rest_framework.exceptions import ValidationError

from apps.message_templates import services
from apps.message_templates.factories import MessageTemplateFactory, standard_components
from apps.message_templates.models import MessageTemplate
from apps.whatsapp.client.errors import (
    InvalidParameterError,
    TemplateError,
    TokenInvalidError,
    TransientError,
)
from apps.whatsapp.factories import WhatsAppBusinessAccountFactory
from apps.whatsapp.models import WhatsAppBusinessAccount
from common.exceptions import UpstreamUnavailable

from .conftest import flatten

pytestmark = pytest.mark.django_db

Status = MessageTemplate.Status


def make_draft(workspace, waba, user=None, **overrides):
    fields = {
        "name": "order_shipped",
        "language": "en",
        "category": "UTILITY",
        "components": standard_components(),
        **overrides,
    }
    return services.create_draft(workspace=workspace, waba=waba, created_by=user, **fields)


# --- Drafts -----------------------------------------------------------------------------------


def test_create_draft_stores_local_draft(workspace, waba, user, fake_graph):
    template = make_draft(workspace, waba, user)

    assert template.status == Status.DRAFT
    assert template.workspace == workspace
    assert template.created_by == user
    assert template.meta_template_id == ""
    assert fake_graph.calls == []


def test_create_draft_rejects_waba_of_other_workspace(workspace, other_waba):
    with pytest.raises(ValidationError) as exc_info:
        make_draft(workspace, other_waba)

    assert "waba" in exc_info.value.detail


def test_create_draft_rejects_duplicate_name_and_language(workspace, waba):
    make_draft(workspace, waba)

    with pytest.raises(ValidationError) as exc_info:
        make_draft(workspace, waba)

    assert "already exists" in flatten(exc_info.value.detail)[0]
    make_draft(workspace, waba, language="hi")  # other language is fine


def test_create_draft_validates_components(workspace, waba):
    with pytest.raises(ValidationError) as exc_info:
        make_draft(workspace, waba, components=[{"type": "BODY", "text": "Hi {{name}} there"}])

    assert "components" in exc_info.value.detail


def test_model_clean_rejects_mismatched_workspace(workspace, other_waba):
    from django.core.exceptions import ValidationError as DjangoValidationError

    template = MessageTemplate(workspace=workspace, waba=other_waba, name="x", language="en")
    with pytest.raises(DjangoValidationError):
        template.clean()


def test_update_blocked_unless_draft_or_rejected():
    template = MessageTemplateFactory(status=Status.APPROVED)

    with pytest.raises(services.TemplateNotEditable):
        services.update_template(template, components=standard_components("Hello there."))


def test_update_rejected_template_keeps_identity():
    template = MessageTemplateFactory(status=Status.REJECTED, meta_template_id="4411")

    services.update_template(template, components=standard_components("Order {{1}} is ready."))
    template.refresh_from_db()
    assert template.components[0]["text"] == "Order {{1}} is ready."
    assert template.status == Status.REJECTED

    with pytest.raises(ValidationError) as exc_info:
        services.update_template(template, name="renamed")
    assert "name" in exc_info.value.detail


# --- Submit -----------------------------------------------------------------------------------


def test_submit_sends_template_to_meta(workspace, waba, fake_graph):
    template = make_draft(workspace, waba)

    template = services.submit(template)

    call = fake_graph.calls_to("create_template")[0]
    assert call.access_token == waba.access_token
    assert call.kwargs["waba_id"] == waba.waba_id
    assert call.kwargs["template"] == {
        "name": "order_shipped",
        "language": "en",
        "category": "UTILITY",
        "components": template.components,
    }
    template.refresh_from_db()
    assert template.status == Status.PENDING
    assert template.meta_template_id in fake_graph.templates
    assert template.submitted_at is not None


def test_submit_resubmits_rejected_template(fake_graph):
    template = MessageTemplateFactory(status=Status.REJECTED, rejected_reason="INVALID_FORMAT")

    template = services.submit(template)

    assert template.status == Status.PENDING
    assert template.rejected_reason == ""


@pytest.mark.parametrize("status", [Status.PENDING, Status.APPROVED, Status.DELETED])
def test_submit_only_drafts_and_rejected(status, fake_graph):
    template = MessageTemplateFactory(status=status)

    with pytest.raises(services.TemplateNotSubmittable):
        services.submit(template)
    assert fake_graph.calls == []


@pytest.mark.parametrize("error_class", [TemplateError, InvalidParameterError])
def test_submit_maps_meta_validation_errors(error_class, fake_graph):
    template = MessageTemplateFactory()
    fake_graph.fail("create_template", error_class("Template name already exists", code=132000))

    with pytest.raises(ValidationError) as exc_info:
        services.submit(template)

    assert "Template name already exists" in flatten(exc_info.value.detail)[0]
    template.refresh_from_db()
    assert template.status == Status.DRAFT
    assert template.meta_template_id == ""


def test_submit_maps_retryable_errors_to_upstream_unavailable(fake_graph):
    template = MessageTemplateFactory()
    fake_graph.fail("create_template", TransientError("Service unavailable", code=2))

    with pytest.raises(UpstreamUnavailable):
        services.submit(template)


def test_submit_maps_other_errors(fake_graph):
    template = MessageTemplateFactory()
    fake_graph.fail("create_template", TokenInvalidError("Session expired", code=190))

    with pytest.raises(services.MetaRequestFailed) as exc_info:
        services.submit(template)
    assert "Session expired" in str(exc_info.value.detail)


@pytest.mark.parametrize(
    "fields",
    [
        {"status": WhatsAppBusinessAccount.Status.DISABLED},
        {"status": WhatsAppBusinessAccount.Status.DISCONNECTED},
        {"access_token": ""},
    ],
)
def test_meta_calls_need_connected_waba(fake_graph, fields):
    waba = WhatsAppBusinessAccountFactory(**fields)
    draft = MessageTemplateFactory(waba=waba)
    submitted = MessageTemplateFactory(waba=waba, meta_template_id="3301", status=Status.APPROVED)

    with pytest.raises(services.WabaNotConnected):
        services.submit(draft)
    with pytest.raises(services.WabaNotConnected):
        services.delete(submitted)
    with pytest.raises(services.WabaNotConnected):
        services.sync_waba(waba)

    assert fake_graph.calls == []
    assert MessageTemplate.objects.filter(pk=submitted.pk).exists()


def test_restricted_waba_can_submit(fake_graph):
    waba = WhatsAppBusinessAccountFactory(status=WhatsAppBusinessAccount.Status.RESTRICTED)

    template = services.submit(MessageTemplateFactory(waba=waba))

    assert template.status == Status.PENDING


# --- Sync -------------------------------------------------------------------------------------


def test_sync_pages_through_templates(waba, fake_graph):
    for n in range(5):
        fake_graph.add_template(waba.waba_id, name=f"promo_{n}")

    result = services.sync_waba(waba, page_size=2)

    assert result == services.SyncResult(created=5, updated=0, deleted=0)
    assert [c.kwargs["after"] for c in fake_graph.calls_to("list_templates")] == [None, "2", "4"]
    assert MessageTemplate.objects.filter(waba=waba, workspace=waba.workspace).count() == 5


def test_sync_updates_existing_and_links_drafts(waba, fake_graph):
    known = MessageTemplateFactory(waba=waba, meta_template_id="7001", status=Status.PENDING)
    draft = MessageTemplateFactory(waba=waba, name="welcome", language="hi")
    fake_graph.add_template(
        waba.waba_id,
        id="7001",
        name=known.name,
        status="REJECTED",
        rejected_reason="INVALID_FORMAT",
        quality_score={"score": "YELLOW", "date": 1700000000},
    )
    fake_graph.add_template(
        waba.waba_id,
        id="7002",
        name="welcome",
        language="hi",
        category="MARKETING",
        rejected_reason="NONE",
        quality_score={"score": "GREEN"},
    )

    result = services.sync_waba(waba)

    assert result == services.SyncResult(created=0, updated=2, deleted=0)
    known.refresh_from_db()
    assert known.status == Status.REJECTED
    assert known.rejected_reason == "INVALID_FORMAT"
    assert known.quality_score == "YELLOW"
    assert known.last_synced_at is not None
    draft.refresh_from_db()
    assert draft.meta_template_id == "7002"
    assert draft.status == Status.APPROVED
    assert draft.category == "MARKETING"
    assert draft.rejected_reason == ""
    assert draft.quality_score == "GREEN"


def test_sync_marks_templates_deleted_at_meta(waba, fake_graph):
    gone = MessageTemplateFactory(waba=waba, meta_template_id="8001", status=Status.APPROVED)
    draft = MessageTemplateFactory(waba=waba)
    other = MessageTemplateFactory(meta_template_id="8002", status=Status.APPROVED)

    result = services.sync_waba(waba)

    assert result.deleted == 1
    gone.refresh_from_db()
    draft.refresh_from_db()
    other.refresh_from_db()
    assert gone.status == Status.DELETED
    assert draft.status == Status.DRAFT
    assert other.status == Status.APPROVED

    assert services.sync_waba(waba).deleted == 0  # idempotent


def test_sync_skips_meta_id_owned_by_another_account(waba, fake_graph):
    MessageTemplateFactory(meta_template_id="9001", status=Status.APPROVED)
    fake_graph.add_template(waba.waba_id, id="9001", name="hijack")

    result = services.sync_waba(waba)

    assert result.created == 0
    assert not MessageTemplate.objects.filter(waba=waba).exists()


# --- Delete -----------------------------------------------------------------------------------


def test_delete_submitted_template_at_meta(waba, fake_graph):
    meta = fake_graph.add_template(waba.waba_id, name="order_update")
    template = MessageTemplateFactory(
        waba=waba, name="order_update", meta_template_id=meta["id"], status=Status.APPROVED
    )

    services.delete(template)

    call = fake_graph.calls_to("delete_template")[0]
    assert call.kwargs == {
        "waba_id": waba.waba_id,
        "name": "order_update",
        "template_id": meta["id"],
    }
    assert not MessageTemplate.objects.filter(pk=template.pk).exists()


def test_delete_draft_is_local_only(fake_graph):
    template = MessageTemplateFactory()

    services.delete(template)

    assert fake_graph.calls == []
    assert not MessageTemplate.objects.filter(pk=template.pk).exists()


def test_delete_keeps_row_when_meta_fails(fake_graph):
    template = MessageTemplateFactory(meta_template_id="5001", status=Status.APPROVED)
    fake_graph.fail("delete_template", TransientError("Try later", code=2))

    with pytest.raises(UpstreamUnavailable):
        services.delete(template)
    assert MessageTemplate.objects.filter(pk=template.pk).exists()


# --- Preview ----------------------------------------------------------------------------------

RICH_COMPONENTS = [
    {
        "type": "HEADER",
        "format": "TEXT",
        "text": "Order {{1}}",
        "example": {"header_text": ["A-102"]},
    },
    {
        "type": "BODY",
        "text": "Hi {{1}}, your order {{2}} has shipped.",
        "example": {"body_text": [["Asha", "A-102"]]},
    },
    {"type": "FOOTER", "text": "Reply STOP to opt out"},
    {
        "type": "BUTTONS",
        "buttons": [
            {"type": "QUICK_REPLY", "text": "Thanks"},
            {
                "type": "URL",
                "text": "Track",
                "url": "https://shop.example.in/t/{{1}}",
                "example": ["https://shop.example.in/t/A-102"],
            },
            {"type": "PHONE_NUMBER", "text": "Call", "phone_number": "+919800041207"},
            {"type": "COPY_CODE", "example": "SAVE20"},
        ],
    },
]


def test_render_preview_fills_variables_and_examples():
    template = MessageTemplateFactory(components=RICH_COMPONENTS)

    preview = services.render_preview(template, ["Ravi"], header_variables=["B-7"])

    assert preview["header"] == {"format": "TEXT", "text": "Order B-7"}
    assert preview["body"] == "Hi Ravi, your order A-102 has shipped."
    assert preview["footer"] == "Reply STOP to opt out"
    assert preview["buttons"] == [
        {"type": "QUICK_REPLY", "text": "Thanks"},
        {"type": "URL", "text": "Track", "url": "https://shop.example.in/t/A-102"},
        {"type": "PHONE_NUMBER", "text": "Call", "phone_number": "+919800041207"},
        {"type": "COPY_CODE", "text": "Copy offer code"},
    ]


def test_render_preview_rejects_extra_variables():
    template = MessageTemplateFactory(components=standard_components("Hello {{1}} there."))

    with pytest.raises(ValidationError):
        services.render_preview(template, ["a", "b"])


def test_render_preview_authentication_template():
    template = MessageTemplateFactory(
        category="AUTHENTICATION",
        components=[
            {"type": "BODY", "add_security_recommendation": True},
            {"type": "FOOTER", "code_expiration_minutes": 5},
            {"type": "BUTTONS", "buttons": [{"type": "OTP", "otp_type": "COPY_CODE"}]},
        ],
    )

    preview = services.render_preview(template, ["482913"])

    assert preview["body"] == (
        "*482913* is your verification code. For your security, do not share this code."
    )
    assert preview["footer"] == "This code expires in 5 minutes."
    assert preview["buttons"] == [{"type": "OTP", "text": "Copy code"}]


# --- Send components --------------------------------------------------------------------------


def test_build_send_components_for_rich_template():
    template = MessageTemplateFactory(
        name="order_shipped", language="en_US", status=Status.APPROVED, components=RICH_COMPONENTS
    )

    payload = services.build_send_components(
        template,
        body_params=["Ravi", "B-7"],
        header_param="B-7",
        button_params={0: "thanks-payload", 1: "B-7", 3: "SAVE20"},
    )

    assert payload == {
        "name": "order_shipped",
        "language": {"code": "en_US"},
        "components": [
            {"type": "header", "parameters": [{"type": "text", "text": "B-7"}]},
            {
                "type": "body",
                "parameters": [{"type": "text", "text": "Ravi"}, {"type": "text", "text": "B-7"}],
            },
            {
                "type": "button",
                "sub_type": "quick_reply",
                "index": "0",
                "parameters": [{"type": "payload", "payload": "thanks-payload"}],
            },
            {
                "type": "button",
                "sub_type": "url",
                "index": "1",
                "parameters": [{"type": "text", "text": "B-7"}],
            },
            {
                "type": "button",
                "sub_type": "copy_code",
                "index": "3",
                "parameters": [{"type": "coupon_code", "coupon_code": "SAVE20"}],
            },
        ],
    }


def test_build_send_components_requires_approved():
    template = MessageTemplateFactory(status=Status.PENDING)

    with pytest.raises(services.TemplateNotApproved) as exc_info:
        services.build_send_components(template, body_params=["a", "b"])
    assert "pending" in str(exc_info.value.detail)


def test_build_send_components_validates_counts():
    template = MessageTemplateFactory(status=Status.APPROVED, components=RICH_COMPONENTS)

    with pytest.raises(ValidationError) as exc_info:
        services.build_send_components(
            template, body_params=["only one"], button_params={2: "x", 9: "y"}
        )

    detail = exc_info.value.detail
    assert set(detail) == {"header_param", "body_params", "button_params"}
    messages = flatten(detail["button_params"])
    assert any("index 9" in m for m in messages)
    assert any("Button 1" in m for m in messages)  # URL variable missing
    assert any("Button 2" in m for m in messages)  # phone button takes no parameters
    assert any("Button 3" in m for m in messages)  # coupon code missing


def test_build_send_components_media_header():
    template = MessageTemplateFactory(
        status=Status.APPROVED,
        components=[{"type": "HEADER", "format": "IMAGE"}, *standard_components("Sale is live!")],
    )

    payload = services.build_send_components(
        template, header_param={"link": "https://cdn.example.in/sale.jpg"}
    )

    assert payload["components"] == [
        {
            "type": "header",
            "parameters": [{"type": "image", "image": {"link": "https://cdn.example.in/sale.jpg"}}],
        }
    ]
    with pytest.raises(ValidationError):
        services.build_send_components(template)


def test_build_send_components_authentication():
    template = MessageTemplateFactory(
        category="AUTHENTICATION",
        status=Status.APPROVED,
        components=[
            {"type": "BODY", "add_security_recommendation": True},
            {"type": "BUTTONS", "buttons": [{"type": "OTP", "otp_type": "COPY_CODE"}]},
        ],
    )

    payload = services.build_send_components(template, body_params=["482913"])

    assert payload["components"] == [
        {"type": "body", "parameters": [{"type": "text", "text": "482913"}]},
        {
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [{"type": "text", "text": "482913"}],
        },
    ]


def test_waba_factory_workspace_matches():
    waba = WhatsAppBusinessAccountFactory()
    template = MessageTemplateFactory(waba=waba)
    assert template.workspace == waba.workspace
