"""Inbox API: media upload (type and size checks) and message media download."""

import uuid

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.inbox import media
from apps.inbox.factories import ConversationFactory, MessageFactory
from apps.inbox.models import MediaAsset, Message
from common.roles import Role
from common.testing import assert_tenant_isolated, make_api_client

pytestmark = pytest.mark.django_db

UPLOAD_URL = "/api/v1/inbox/media/"
KB = 1024

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"\x00" * 64
OGG = b"OggS" + b"\x00" * 64


def webp(size: int, *, animated: bool) -> bytes:
    if animated:
        chunk = b"VP8X" + (10).to_bytes(4, "little") + bytes([0x02]) + b"\x00" * 9
    else:
        chunk = b"VP8 " + (10).to_bytes(4, "little") + b"\x00" * 10
    head = b"RIFF" + (size - 8).to_bytes(4, "little") + b"WEBP" + chunk
    return head + b"\x00" * (size - len(head))


def upload(client, name, content, content_type):
    file = SimpleUploadedFile(name, content, content_type)
    return client.post(UPLOAD_URL, {"file": file}, format="multipart")


def media_url(message) -> str:
    return f"/api/v1/inbox/messages/{message.pk}/media/"


# --- Upload -------------------------------------------------------------------------------------


def test_upload_image(auth_client, workspace):
    client = auth_client(Role.AGENT)

    response = upload(client, "photo.jpg", JPEG, "image/jpeg")

    assert response.status_code == 201, response.content
    body = response.json()
    assert set(body) == {"id", "mime_type", "file_name", "size", "created_at"}
    assert (body["mime_type"], body["file_name"], body["size"]) == (
        "image/jpeg",
        "photo.jpg",
        len(JPEG),
    )
    asset = MediaAsset.objects.get(pk=body["id"])
    assert asset.workspace == workspace
    assert asset.uploaded_by is not None
    assert "photo" not in asset.file.name  # stored under a random name
    with asset.file.open("rb") as handle:
        assert handle.read() == JPEG


@pytest.mark.parametrize(
    ("name", "content", "content_type", "stored_type"),
    [
        ("scan.png", PNG, "image/png", "image/png"),
        ("invoice.pdf", PDF, "application/pdf", "application/pdf"),
        ("note.ogg", OGG, "audio/ogg; codecs=opus", "audio/ogg"),
        ("clip.mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32, "video/mp4", "video/mp4"),
        ("notes.txt", b"hello", "text/plain", "text/plain"),
        (
            "sheet.xlsx",
            b"PK\x03\x04" + b"\x00" * 32,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    ],
)
def test_supported_types(auth_client, name, content, content_type, stored_type):
    response = upload(auth_client(Role.AGENT), name, content, content_type)

    assert response.status_code == 201, response.content
    assert response.json()["mime_type"] == stored_type


@pytest.mark.parametrize(
    "content_type", ["image/gif", "text/html", "image/svg+xml", "application/x-msdownload", ""]
)
def test_unsupported_types_are_rejected(auth_client, content_type):
    response = upload(auth_client(Role.AGENT), "file.bin", JPEG, content_type)

    assert response.status_code == 400
    assert "file" in response.json()["error"]["details"]
    assert not MediaAsset.objects.exists()


@pytest.mark.parametrize(
    ("content", "content_type"),
    [(JPEG, "image/png"), (PNG, "image/jpeg"), (b"<html></html>", "application/pdf")],
)
def test_content_must_match_the_declared_type(auth_client, content, content_type):
    response = upload(auth_client(Role.AGENT), "file", content, content_type)

    assert response.status_code == 400
    assert "does not match" in str(response.json()["error"]["details"]["file"])


def test_size_limit_from_settings(auth_client, settings):
    settings.WHATSAPP_MEDIA_MAX_BYTES = {**settings.WHATSAPP_MEDIA_MAX_BYTES, "image": 8}

    response = upload(auth_client(Role.AGENT), "photo.jpg", JPEG, "image/jpeg")

    assert response.status_code == 400
    assert "larger than" in str(response.json()["error"]["details"]["file"])


def test_meta_limits_cap_larger_settings(settings):
    settings.WHATSAPP_MEDIA_MAX_BYTES = dict.fromkeys(settings.WHATSAPP_MEDIA_MAX_BYTES, 10**9)

    assert media.max_bytes("image") == 5 * 1024 * 1024
    assert media.max_bytes("video") == media.max_bytes("audio") == 16 * 1024 * 1024
    assert media.max_bytes("document") == 100 * 1024 * 1024
    assert media.max_bytes("sticker") == 500 * KB
    assert media.max_bytes("sticker", animated=False) == 100 * KB


def test_static_stickers_are_limited_to_100_kb(auth_client):
    client = auth_client(Role.AGENT)

    static = upload(client, "s.webp", webp(100 * KB + 1, animated=False), "image/webp")
    animated = upload(client, "a.webp", webp(100 * KB + 1, animated=True), "image/webp")
    small = upload(client, "s.webp", webp(100 * KB, animated=False), "image/webp")

    assert static.status_code == 400
    assert animated.status_code == 201, animated.content
    assert small.status_code == 201


def test_empty_file_is_rejected(auth_client):
    response = upload(auth_client(Role.AGENT), "empty.pdf", b"", "application/pdf")

    assert response.status_code == 400


def test_file_name_is_sanitised(auth_client):
    response = upload(auth_client(Role.AGENT), "in|voice<1>?.pdf", PDF, "application/pdf")

    assert response.status_code == 201, response.content
    assert response.json()["file_name"] == "in_voice_1__.pdf"


def test_upload_needs_agent(auth_client):
    response = upload(auth_client(Role.VIEWER), "a.pdf", PDF, "application/pdf")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_role"


def test_upload_non_member_gets_404(user, other_workspace):
    response = upload(make_api_client(user, other_workspace), "a.pdf", PDF, "application/pdf")

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("photo.jpg", "photo.jpg"),
        ("C:\\Users\\me\\invoice.pdf", "invoice.pdf"),
        ("a\r\nb.pdf", "a__b.pdf"),
        ('..\\..\\etc\\pa"ss;wd.pdf', "pa_ss_wd.pdf"),
        ("../../etc/passwd", "passwd"),
        ("", "file"),
        ("...", "file"),
        ("x" * 300 + ".pdf", "x" * 251 + ".pdf"),
    ],
)
def test_safe_file_name(value, expected):
    assert media.safe_file_name(value) == expected


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


# --- Download -----------------------------------------------------------------------------------


def stored_message(conversation, content, **fields):
    fields.setdefault("type", Message.Type.IMAGE)
    fields.setdefault("mime_type", "image/jpeg")
    fields.setdefault("file_name", "photo.jpg")
    return MessageFactory(
        conversation=conversation,
        inbound=True,
        size=len(content),
        file=ContentFile(content, name="stored.bin"),
        **fields,
    )


def body_of(response) -> bytes:
    return b"".join(response.streaming_content)


def test_viewer_downloads_inline_image(auth_client, conversation):
    message = stored_message(conversation, JPEG)

    response = auth_client(Role.VIEWER).get(media_url(message))

    assert response.status_code == 200
    assert body_of(response) == JPEG
    assert response["Content-Type"] == "image/jpeg"
    assert response["Content-Disposition"] == 'inline; filename="photo.jpg"'
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "sandbox" in response["Content-Security-Policy"]


@pytest.mark.parametrize(
    ("mime_type", "file_name", "disposition"),
    [
        ("application/pdf", "invoice.pdf", 'attachment; filename="invoice.pdf"'),
        ("text/html", "page.html", 'attachment; filename="page.html"'),
        ("application/pdf", 'bad"\r\nname.pdf', 'attachment; filename="bad___name.pdf"'),
        ("image/svg+xml", "logo.svg", 'attachment; filename="logo.svg"'),
    ],
)
def test_other_types_download_as_attachments(
    auth_client, conversation, mime_type, file_name, disposition
):
    message = stored_message(
        conversation, PDF, type=Message.Type.DOCUMENT, mime_type=mime_type, file_name=file_name
    )

    response = auth_client(Role.VIEWER).get(media_url(message))

    assert response.status_code == 200
    assert response["Content-Disposition"] == disposition
    if mime_type == "image/svg+xml":
        assert response["Content-Type"] == "application/octet-stream"


def test_invalid_stored_mime_type_is_served_as_octet_stream(auth_client, conversation):
    message = stored_message(conversation, PDF, mime_type="text/html\r\nX-Evil: 1", file_name="")

    response = auth_client().get(media_url(message))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/octet-stream"
    assert response["Content-Disposition"].startswith('attachment; filename="image-')


def test_download_without_a_stored_file_is_404(auth_client, conversation):
    message = MessageFactory(conversation=conversation, inbound=True, type=Message.Type.IMAGE)

    assert auth_client().get(media_url(message)).status_code == 404
    assert auth_client().get(f"/api/v1/inbox/messages/{uuid.uuid4()}/media/").status_code == 404


def test_download_is_tenant_isolated(auth_client, other_workspace):
    foreign = stored_message(ConversationFactory(workspace=other_workspace), JPEG)

    assert_tenant_isolated(
        auth_client(Role.ADMIN), object_id=foreign.pk, detail_url=media_url(foreign)
    )


def test_uploaded_media_round_trip(auth_client, conversation):
    client = auth_client(Role.AGENT)
    asset_id = upload(client, "invoice.pdf", PDF, "application/pdf").json()["id"]

    sent = client.post(
        f"/api/v1/inbox/conversations/{conversation.pk}/messages/",
        {"type": "media", "media_id": asset_id},
        format="json",
    )
    assert sent.status_code == 201, sent.content
    download = client.get(sent.json()["media"]["download_url"])

    assert download.status_code == 200
    assert body_of(download) == PDF
    assert download["Content-Disposition"] == 'attachment; filename="invoice.pdf"'
