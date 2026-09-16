"""S3 media storage (DigitalOcean Spaces): private signed URLs, public product image URLs,
worker reads through the storage, and prod settings refusing incomplete credentials.

Buckets are mocked with moto (no network); presigned URLs are computed locally by botocore.
"""

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import boto3
import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from moto import mock_aws

from apps.catalog import services as catalog_services
from apps.catalog.factories import ProductFactory
from apps.contacts.models import ContactImport
from apps.inbox import tasks as inbox_tasks
from apps.inbox.factories import ConversationFactory, MessageFactory
from apps.inbox.models import MediaAsset, Message
from apps.whatsapp.client.fake import FakeGraphClient
from common.storage import PrivateMediaStorage, PublicMediaStorage, public_media_storage

BACKEND_DIR = Path(__file__).resolve().parents[2]
BUCKET = "upchatz-media-test"
REGION = "us-east-1"
PUBLIC_READ = "http://acs.amazonaws.com/groups/global/AllUsers"

S3_SETTINGS = {
    "AWS_STORAGE_BUCKET_NAME": BUCKET,
    "AWS_S3_ENDPOINT_URL": None,  # moto intercepts the AWS endpoint only
    "AWS_S3_REGION_NAME": REGION,
    "AWS_ACCESS_KEY_ID": "test-access-key",
    "AWS_SECRET_ACCESS_KEY": "test-secret-key",
    "AWS_S3_CUSTOM_DOMAIN": None,
    "AWS_QUERYSTRING_EXPIRE": 600,
    "AWS_S3_SIGNATURE_VERSION": "s3v4",
    "AWS_S3_ADDRESSING_STYLE": "virtual",
}
S3_STORAGES = {
    "default": {"BACKEND": "common.storage.PrivateMediaStorage"},
    "public_media": {"BACKEND": "common.storage.PublicMediaStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@pytest.fixture
def s3():
    """A mocked bucket with the S3 storage settings active; yields a boto3 client."""
    with mock_aws(), override_settings(**S3_SETTINGS, STORAGES=S3_STORAGES):
        client = boto3.client(
            "s3",
            region_name=REGION,
            aws_access_key_id="test-access-key",
            aws_secret_access_key="test-secret-key",
        )
        client.create_bucket(Bucket=BUCKET)
        yield client


def is_public(client, key: str) -> bool:
    grants = client.get_object_acl(Bucket=BUCKET, Key=key)["Grants"]
    return any(
        grant["Grantee"].get("URI") == PUBLIC_READ and grant["Permission"] == "READ"
        for grant in grants
    )


def test_private_files_get_signed_urls_and_private_acl(s3):
    storage = PrivateMediaStorage()
    name = storage.save("contact_imports/2026/09/contacts.csv", ContentFile(b"phone\n"))

    assert not is_public(s3, name)
    parts = urlsplit(storage.url(name))
    query = parse_qs(parts.query)
    assert parts.scheme == "https"
    assert BUCKET in parts.netloc
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert query["X-Amz-Expires"] == ["600"]
    assert "X-Amz-Signature" in query


def test_private_files_never_overwrite(s3):
    storage = PrivateMediaStorage()
    first = storage.save("contact_imports/2026/09/contacts.csv", ContentFile(b"one"))
    second = storage.save("contact_imports/2026/09/contacts.csv", ContentFile(b"two"))

    assert first != second
    with storage.open(first) as handle:
        assert handle.read() == b"one"


def test_private_storage_ignores_cdn_domain(s3, settings):
    settings.AWS_S3_CUSTOM_DOMAIN = "media.upchatz.example"
    storage = PrivateMediaStorage()
    url = storage.url("inbox/media/2026/09/photo.jpg")

    assert "media.upchatz.example" not in url
    assert "X-Amz-Signature" in url


def test_spaces_endpoint_signs_urls_offline(settings):
    """URLs for DigitalOcean Spaces are signed locally; nothing is sent to the endpoint."""
    settings.AWS_S3_ENDPOINT_URL = "https://blr1.digitaloceanspaces.com"
    settings.AWS_S3_REGION_NAME = "blr1"
    settings.AWS_STORAGE_BUCKET_NAME = BUCKET
    settings.AWS_ACCESS_KEY_ID = "test-access-key"
    settings.AWS_SECRET_ACCESS_KEY = "test-secret-key"
    settings.AWS_S3_SIGNATURE_VERSION = "s3v4"
    settings.AWS_S3_ADDRESSING_STYLE = "virtual"

    url = urlsplit(PrivateMediaStorage().url("inbox/assets/2026/09/a.pdf"))

    assert url.netloc == f"{BUCKET}.blr1.digitaloceanspaces.com"
    assert "X-Amz-Signature" in parse_qs(url.query)


def test_public_files_are_public_read_with_unsigned_urls(s3, settings):
    settings.PUBLIC_MEDIA_BASE_URL = ""
    storage = PublicMediaStorage()
    name = storage.save("catalog/products/w/ab/abc.jpg", ContentFile(b"\xff\xd8\xff"))

    assert is_public(s3, name)
    url = storage.url(name)
    assert url.startswith("https://")
    assert url.endswith("/catalog/products/w/ab/abc.jpg")
    assert "X-Amz-" not in url


def test_public_urls_honour_public_media_base_url(s3, settings):
    settings.PUBLIC_MEDIA_BASE_URL = "https://cdn.upchatz.example/media/"

    url = PublicMediaStorage().url("catalog/products/w/ab/a b.jpg")

    assert url == "https://cdn.upchatz.example/media/catalog/products/w/ab/a%20b.jpg"


def test_public_urls_use_custom_domain_without_base_url(s3, settings):
    settings.PUBLIC_MEDIA_BASE_URL = ""
    storage = PublicMediaStorage(custom_domain="media.upchatz.example")

    assert storage.url("catalog/x.jpg") == "https://media.upchatz.example/catalog/x.jpg"


def test_public_media_storage_uses_the_configured_alias(s3):
    assert isinstance(public_media_storage(), PublicMediaStorage)


def test_public_media_storage_falls_back_to_default():
    assert public_media_storage() is default_storage


@pytest.mark.django_db
def test_product_image_url_comes_from_public_storage(s3, settings, workspace, monkeypatch):
    settings.PUBLIC_MEDIA_BASE_URL = ""
    storage = PublicMediaStorage()
    product = ProductFactory(workspace=workspace)
    product.image.name = storage.save(
        f"catalog/products/{workspace.pk}/ab/abc.jpg", ContentFile(b"x")
    )
    monkeypatch.setattr(product.image, "storage", storage)

    url = catalog_services.public_image_url(product)

    assert url == storage.url(product.image.name)
    assert url.startswith("https://") and "X-Amz-" not in url

    settings.PUBLIC_MEDIA_BASE_URL = "https://cdn.upchatz.example"
    assert catalog_services.public_image_url(product) == (
        f"https://cdn.upchatz.example/catalog/products/{workspace.pk}/ab/abc.jpg"
    )


@pytest.mark.django_db
def test_contact_import_reads_the_csv_from_s3(s3, auth_client, django_capture_on_commit_callbacks):
    """The API stores the upload in the bucket; the (eager) worker task reads it back."""
    body = {"file": SimpleUploadedFile("c.csv", b"phone,name\n+919812345678,Asha\n", "text/csv")}
    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client().post(reverse("contacts:import-list"), body, format="multipart")

    assert response.status_code == 201, response.content
    job = ContactImport.objects.get(pk=response.json()["id"])
    assert job.status == ContactImport.Status.COMPLETED, job.errors
    assert job.created_count == 1
    keys = [item["Key"] for item in s3.list_objects_v2(Bucket=BUCKET)["Contents"]]
    assert keys == [job.file.name]
    assert not is_public(s3, job.file.name)


@pytest.mark.django_db
def test_inbox_media_streams_from_s3(s3, auth_client, workspace):
    conversation = ConversationFactory(workspace=workspace)
    message = MessageFactory(
        conversation=conversation,
        workspace=workspace,
        type=Message.Type.IMAGE,
        mime_type="image/jpeg",
    )
    message.file.save("photo.jpg", ContentFile(b"\xff\xd8\xff remote jpeg"), save=True)

    url = reverse("inbox:message-media", kwargs={"pk": message.pk})
    response = auth_client().get(url)

    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"\xff\xd8\xff remote jpeg"


@pytest.mark.django_db
def test_worker_uploads_an_api_stored_asset_from_s3(s3, auth_client):
    """The API stores an inbox asset in the bucket; the worker reads it to upload to Meta."""
    body = {"file": SimpleUploadedFile("offer.pdf", b"%PDF-1.4 remote", "application/pdf")}
    response = auth_client().post(reverse("inbox:media-list"), body, format="multipart")
    assert response.status_code == 201, response.content
    asset = MediaAsset.objects.get(pk=response.json()["id"])
    assert not is_public(s3, asset.file.name)

    fake = FakeGraphClient()
    media_id = inbox_tasks._meta_media_id(asset, "1234567890", fake)

    assert fake.media[media_id]["content"] == b"%PDF-1.4 remote"


def run_prod_settings(**overrides) -> subprocess.CompletedProcess:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("AWS_", "DJANGO_", "MEDIA_"))
    }
    env.update(
        {
            "DJANGO_SECRET_KEY": "prod-test-secret",
            "TOKEN_ENCRYPTION_KEYS": "ZmFrZS1rZXktZm9yLXRlc3RzLW9ubHktMDAwMDAwMDA=",
            "WS_ALLOWED_ORIGINS": "https://upchatz.example",
            "SENTRY_DSN": "",
            "MEDIA_STORAGE": "s3",
            "AWS_STORAGE_BUCKET_NAME": "",
            "AWS_ACCESS_KEY_ID": "",
            "AWS_SECRET_ACCESS_KEY": "",
        }
    )
    env.update(overrides)
    return subprocess.run(
        [sys.executable, "-c", "import config.settings.prod"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_prod_settings_refuse_s3_without_credentials():
    result = run_prod_settings(AWS_STORAGE_BUCKET_NAME=BUCKET)

    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert "MEDIA_STORAGE=s3 requires AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY" in result.stderr


def test_prod_settings_accept_complete_s3_config():
    result = run_prod_settings(
        AWS_STORAGE_BUCKET_NAME=BUCKET,
        AWS_ACCESS_KEY_ID="test-access-key",
        AWS_SECRET_ACCESS_KEY="test-secret-key",
    )

    assert result.returncode == 0, result.stderr


def test_unknown_media_storage_is_rejected():
    result = run_prod_settings(MEDIA_STORAGE="ftp")

    assert result.returncode != 0
    assert "MEDIA_STORAGE must be 'local' or 's3'" in result.stderr
