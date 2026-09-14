import pytest
from django.urls import reverse

from apps.message_templates.factories import MessageTemplateFactory, standard_components
from apps.message_templates.models import MessageTemplate
from apps.whatsapp.client.errors import TemplateError
from apps.whatsapp.factories import WhatsAppBusinessAccountFactory
from apps.whatsapp.models import WhatsAppBusinessAccount
from common.roles import Role
from common.testing import assert_tenant_isolated, result_ids

pytestmark = pytest.mark.django_db

Status = MessageTemplate.Status
LIST = reverse("message_templates:template-list")
SYNC = reverse("message_templates:template-sync")


def detail_url(template):
    return reverse("message_templates:template-detail", args=[template.pk])


def action_url(template, name):
    return reverse(f"message_templates:template-{name}", args=[template.pk])


def create_payload(waba, **overrides):
    return {
        "waba": str(waba.pk),
        "name": "order_shipped",
        "language": "en",
        "category": "UTILITY",
        "components": standard_components(),
        **overrides,
    }


def test_urls_are_mounted():
    assert LIST == "/api/v1/templates/"
    assert SYNC == "/api/v1/templates/sync/"


def test_list_is_tenant_isolated(auth_client, other_waba):
    foreign = MessageTemplateFactory(waba=other_waba)

    assert_tenant_isolated(
        auth_client(), object_id=foreign.pk, list_url=LIST, detail_url=detail_url(foreign)
    )


def test_viewer_can_list_and_retrieve(auth_client, waba):
    template = MessageTemplateFactory(waba=waba)
    client = auth_client(Role.VIEWER)

    response = client.get(LIST)
    assert response.status_code == 200
    assert result_ids(response) == {str(template.pk)}

    response = client.get(detail_url(template))
    assert response.status_code == 200
    body = response.json()
    assert body["waba"] == str(waba.pk)
    assert body["status"] == "DRAFT"
    assert "access_token" not in str(body)


def test_list_filters_and_search(auth_client, waba):
    approved = MessageTemplateFactory(waba=waba, name="diwali_sale", status=Status.APPROVED)
    MessageTemplateFactory(waba=waba, name="order_update", status=Status.DRAFT)
    client = auth_client(Role.VIEWER)

    assert result_ids(client.get(LIST, {"status": "APPROVED"})) == {str(approved.pk)}
    assert result_ids(client.get(LIST, {"search": "diwali"})) == {str(approved.pk)}
    assert result_ids(client.get(LIST, {"waba": str(waba.pk), "language": "en"})) == {
        str(t.pk) for t in MessageTemplate.objects.all()
    }


def test_admin_creates_draft(auth_client, waba, fake_graph):
    response = auth_client(Role.ADMIN).post(LIST, create_payload(waba), format="json")

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "DRAFT"
    template = MessageTemplate.objects.get(pk=body["id"])
    assert template.workspace == waba.workspace
    assert template.created_by is not None
    assert fake_graph.calls == []


@pytest.mark.parametrize("role", [Role.AGENT, Role.VIEWER])
def test_non_admin_cannot_write(auth_client, waba, role):
    template = MessageTemplateFactory(waba=waba)
    client = auth_client(role)

    assert client.post(LIST, create_payload(waba), format="json").status_code == 403
    assert client.patch(detail_url(template), {"language": "hi"}).status_code == 403
    assert client.delete(detail_url(template)).status_code == 403
    assert client.post(action_url(template, "submit")).status_code == 403
    assert client.post(SYNC).status_code == 403


def test_create_rejects_invalid_components(auth_client, waba):
    payload = create_payload(waba, components=[{"type": "BODY", "text": "Hi {{name}} there"}])

    response = auth_client(Role.ADMIN).post(LIST, payload, format="json")

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid"
    assert "named variables" in error["details"]["components"][0]


def test_create_rejects_waba_of_other_workspace(auth_client, other_waba):
    response = auth_client().post(LIST, create_payload(other_waba), format="json")

    assert response.status_code == 400
    assert "waba" in response.json()["error"]["details"]


def test_patch_draft(auth_client, waba):
    template = MessageTemplateFactory(waba=waba)

    response = auth_client().patch(
        detail_url(template),
        {"components": standard_components("Your order {{1}} is on the way.")},
        format="json",
    )

    assert response.status_code == 200, response.content
    template.refresh_from_db()
    assert template.components[0]["text"] == "Your order {{1}} is on the way."


def test_patch_blocked_when_approved(auth_client, waba):
    template = MessageTemplateFactory(waba=waba, status=Status.APPROVED, meta_template_id="31")

    response = auth_client().patch(detail_url(template), {"components": []}, format="json")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "template_not_editable"


def test_submit(auth_client, waba, fake_graph):
    template = MessageTemplateFactory(waba=waba)

    response = auth_client(Role.ADMIN).post(action_url(template, "submit"))

    assert response.status_code == 200, response.content
    assert response.json()["status"] == "PENDING"
    assert response.json()["meta_template_id"]
    assert len(fake_graph.calls_to("create_template")) == 1


def test_submit_meta_error_is_400(auth_client, waba, fake_graph):
    template = MessageTemplateFactory(waba=waba)
    fake_graph.fail("create_template", TemplateError("Body has too many variables", code=132005))

    response = auth_client().post(action_url(template, "submit"))

    assert response.status_code == 400
    assert response.json()["error"]["details"]["meta"] == ["Body has too many variables"]


def test_submit_approved_is_409(auth_client, waba):
    template = MessageTemplateFactory(waba=waba, status=Status.APPROVED)

    response = auth_client().post(action_url(template, "submit"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "template_not_submittable"


def test_viewer_can_preview(auth_client, waba):
    template = MessageTemplateFactory(waba=waba)

    response = auth_client(Role.VIEWER).post(
        action_url(template, "preview"), {"variables": ["Asha", "A-7"]}, format="json"
    )

    assert response.status_code == 200, response.content
    assert response.json() == {
        "header": None,
        "body": "Hi Asha, your order A-7 has shipped.",
        "footer": None,
        "buttons": [],
    }


def test_foreign_template_actions_are_404(auth_client, other_waba):
    template = MessageTemplateFactory(waba=other_waba)
    client = auth_client()

    assert client.post(action_url(template, "preview"), {}, format="json").status_code == 404
    assert client.post(action_url(template, "submit")).status_code == 404
    assert client.delete(detail_url(template)).status_code == 404


def test_sync_all_active_wabas(auth_client, workspace, waba, other_waba, fake_graph):
    WhatsAppBusinessAccountFactory(
        workspace=workspace, status=WhatsAppBusinessAccount.Status.DISCONNECTED
    )
    fake_graph.add_template(waba.waba_id, id="61", name="welcome")
    fake_graph.add_template(other_waba.waba_id, id="62", name="not_mine")

    response = auth_client(Role.ADMIN).post(SYNC, {}, format="json")

    assert response.status_code == 202, response.content
    assert response.json() == {"queued": [str(waba.pk)]}
    assert list(MessageTemplate.objects.values_list("meta_template_id", flat=True)) == ["61"]


@pytest.mark.parametrize("use_meta_id", [False, True])
def test_sync_one_waba(auth_client, waba, fake_graph, use_meta_id):
    waba_id = waba.waba_id if use_meta_id else str(waba.pk)

    response = auth_client().post(SYNC, {"waba_id": waba_id}, format="json")

    assert response.status_code == 202
    assert response.json() == {"queued": [str(waba.pk)]}
    assert fake_graph.calls_to("list_templates")[0].kwargs["waba_id"] == waba.waba_id


def test_sync_foreign_waba_is_404(auth_client, other_waba, fake_graph):
    response = auth_client().post(SYNC, {"waba_id": str(other_waba.pk)}, format="json")

    assert response.status_code == 404
    assert fake_graph.calls == []


def test_admin_deletes_template(auth_client, waba, fake_graph):
    meta = fake_graph.add_template(waba.waba_id, name="old_offer")
    template = MessageTemplateFactory(
        waba=waba, name="old_offer", meta_template_id=meta["id"], status=Status.APPROVED
    )

    response = auth_client(Role.ADMIN).delete(detail_url(template))

    assert response.status_code == 204
    assert not MessageTemplate.objects.filter(pk=template.pk).exists()
    assert fake_graph.calls_to("delete_template")[0].kwargs["template_id"] == meta["id"]
