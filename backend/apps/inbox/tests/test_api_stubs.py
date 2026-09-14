"""Inbox API contract stubs: roles, validation and the 501 envelope. ws-ticket is real."""

import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from common.roles import Role
from common.testing import make_api_client
from common.ws_auth import WS_PATH, consume_ticket

pytestmark = pytest.mark.django_db

BASE = "/api/v1/inbox"
CONVERSATION = f"{BASE}/conversations/{uuid.uuid4()}"


def assert_not_implemented(response):
    assert response.status_code == 501, response.content
    assert response.json()["error"]["code"] == "not_implemented"


def assert_insufficient_role(response):
    assert response.status_code == 403, response.content
    assert response.json()["error"]["code"] == "insufficient_role"


VIEWER_READS = [
    f"{BASE}/conversations/",
    f"{CONVERSATION}/",
    f"{CONVERSATION}/messages/",
    f"{CONVERSATION}/notes/",
    f"{BASE}/messages/{uuid.uuid4()}/media/",
]

AGENT_WRITES = [
    (f"{BASE}/conversations/", {"contact_id": str(uuid.uuid4())}),
    (f"{CONVERSATION}/assign/", {"assignee_id": None}),
    (f"{CONVERSATION}/close/", {}),
    (f"{CONVERSATION}/reopen/", {}),
    (f"{CONVERSATION}/read/", {}),
    (f"{CONVERSATION}/messages/", {"type": "text", "text": "Hello"}),
    (f"{CONVERSATION}/notes/", {"body": "Called the customer"}),
]


@pytest.mark.parametrize("url", VIEWER_READS)
def test_viewer_reads_are_stubbed(auth_client, url):
    assert_not_implemented(auth_client(Role.VIEWER).get(url))


@pytest.mark.parametrize(("url", "body"), AGENT_WRITES)
def test_writes_need_agent(auth_client, url, body):
    assert_insufficient_role(auth_client(Role.VIEWER).post(url, body, format="json"))
    assert_not_implemented(auth_client(Role.AGENT).post(url, body, format="json"))


@pytest.mark.parametrize("url", [f"{BASE}/conversations/", f"{CONVERSATION}/messages/"])
def test_non_members_get_404(user, other_workspace, url):
    response = make_api_client(user, other_workspace).get(url)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "workspace_not_found"


def test_anonymous_gets_401(api_client, workspace):
    response = make_api_client(None, workspace).get(f"{BASE}/conversations/")

    assert response.status_code == 401


def test_send_message_idempotency_key_is_accepted(auth_client):
    response = auth_client(Role.AGENT).post(
        f"{CONVERSATION}/messages/",
        {"type": "template", "template_id": str(uuid.uuid4()), "body_params": ["Asha"]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="retry-1",
    )

    assert_not_implemented(response)


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"type": "text"}, "text"),
        ({"type": "text", "text": "   "}, "text"),
        ({"type": "template"}, "template_id"),
        ({"type": "media"}, "media_id"),
        ({"type": "location"}, "type"),
        (
            {"type": "template", "template_id": str(uuid.uuid4()), "button_params": {"x": "1"}},
            "button_params",
        ),
    ],
)
def test_send_message_validation(auth_client, body, field):
    response = auth_client(Role.AGENT).post(f"{CONVERSATION}/messages/", body, format="json")

    assert response.status_code == 400, response.content
    assert field in response.json()["error"]["details"]


def test_blank_note_is_rejected(auth_client):
    response = auth_client(Role.AGENT).post(f"{CONVERSATION}/notes/", {"body": "  "}, format="json")

    assert response.status_code == 400
    assert "body" in response.json()["error"]["details"]


def test_start_conversation_needs_contact(auth_client):
    response = auth_client(Role.AGENT).post(f"{BASE}/conversations/", {}, format="json")

    assert response.status_code == 400
    assert "contact_id" in response.json()["error"]["details"]


def test_media_upload_is_stubbed(auth_client):
    upload = SimpleUploadedFile("photo.jpg", b"\xff\xd8\xff" + b"0" * 10, "image/jpeg")

    response = auth_client(Role.AGENT).post(f"{BASE}/media/", {"file": upload}, format="multipart")

    assert_not_implemented(response)


def test_media_upload_enforces_meta_size_limits(auth_client, settings):
    settings.WHATSAPP_MEDIA_MAX_BYTES = {**settings.WHATSAPP_MEDIA_MAX_BYTES, "image": 8}
    upload = SimpleUploadedFile("photo.jpg", b"0" * 9, "image/jpeg")

    response = auth_client(Role.AGENT).post(f"{BASE}/media/", {"file": upload}, format="multipart")

    assert response.status_code == 400
    assert "file" in response.json()["error"]["details"]


def test_media_upload_needs_agent(auth_client):
    upload = SimpleUploadedFile("a.pdf", b"%PDF", "application/pdf")

    response = auth_client(Role.VIEWER).post(f"{BASE}/media/", {"file": upload}, format="multipart")

    assert_insufficient_role(response)


@pytest.mark.parametrize(
    ("content_type", "kind"),
    [
        ("image/jpeg", "image"),
        ("image/webp", "sticker"),
        ("video/mp4", "video"),
        ("audio/ogg", "audio"),
        ("application/pdf", "document"),
        ("", "document"),
    ],
)
def test_media_kind(content_type, kind):
    from apps.inbox.serializers import media_kind

    assert media_kind(content_type) == kind


@pytest.mark.parametrize("role", [Role.VIEWER, Role.AGENT, Role.ADMIN, Role.OWNER])
def test_ws_ticket_for_any_member(auth_client, workspace, settings, role):
    client = auth_client(role)

    response = client.post(f"{BASE}/ws-ticket/")

    assert response.status_code == 200, response.content
    assert response["Cache-Control"] == "no-store"
    body = response.json()
    assert body["expires_in"] == settings.WS_TICKET_TTL
    assert body["path"] == WS_PATH
    user_id, workspace_id = consume_ticket(body["ticket"])
    assert workspace_id == workspace.pk
    assert user_id == response.wsgi_request.user.pk


def test_ws_tickets_are_unique(auth_client):
    client = auth_client()

    first = client.post(f"{BASE}/ws-ticket/").json()["ticket"]
    second = client.post(f"{BASE}/ws-ticket/").json()["ticket"]

    assert first != second


def test_ws_ticket_non_member_gets_404(user, other_workspace):
    response = make_api_client(user, other_workspace).post(f"{BASE}/ws-ticket/")

    assert response.status_code == 404
