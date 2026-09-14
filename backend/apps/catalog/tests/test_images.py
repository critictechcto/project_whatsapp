"""Product image upload: checks run on the decoded image, storage uses content-hashed names."""

import hashlib
import io
import os

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.catalog.factories import MetaCatalogFactory, ProductFactory
from common.roles import Role

from .conftest import PRODUCTS, detail

pytestmark = pytest.mark.django_db


def image_bytes(width: int, height: int, image_format: str = "PNG", *, noise=False) -> bytes:
    if noise:
        image = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    else:
        image = Image.new("RGB", (width, height), (212, 120, 40))
    buffer = io.BytesIO()
    options = {"compress_level": 0} if image_format == "PNG" else {}
    image.save(buffer, image_format, **options)
    return buffer.getvalue()


def upload(content: bytes, name: str = "photo.png", content_type: str = "image/png"):
    return SimpleUploadedFile(name, content, content_type=content_type)


def image_url(product) -> str:
    return detail(PRODUCTS, product, "image/")


def post_image(client, product, file):
    return client.post(image_url(product), {"file": file}, format="multipart")


def assert_file_error(response, fragment: str) -> None:
    assert response.status_code == 400, response.content
    [message] = response.json()["error"]["details"]["file"]
    assert fragment in message


def test_upload_stores_a_content_hashed_public_image(admin, workspace):
    product = ProductFactory(workspace=workspace)
    content = image_bytes(600, 800)
    digest = hashlib.sha256(content).hexdigest()

    response = post_image(admin, product, upload(content))

    assert response.status_code == 200, response.content
    name = f"catalog/products/{workspace.pk}/{digest[:2]}/{digest}.png"
    assert response.json()["image_url"] == f"https://media.testserver/{name}"
    product.refresh_from_db()
    assert product.image.name == name
    assert default_storage.exists(name)

    again = post_image(admin, ProductFactory(workspace=workspace), upload(content, "copy.png"))
    assert again.json()["image_url"] == f"https://media.testserver/{name}"


def test_the_decoded_format_wins_over_the_client_name_and_type(admin, workspace):
    product = ProductFactory(workspace=workspace)

    response = post_image(
        admin, product, upload(image_bytes(500, 500, "JPEG"), "notes.txt", "text/plain")
    )

    assert response.status_code == 200, response.content
    assert response.json()["image_url"].endswith(".jpg")


def test_small_images_are_rejected(admin, workspace):
    product = ProductFactory(workspace=workspace)

    response = post_image(admin, product, upload(image_bytes(499, 900)))

    assert_file_error(response, "at least 500x500")
    product.refresh_from_db()
    assert not product.image


def test_large_images_are_rejected(admin, workspace):
    content = image_bytes(1700, 1700, noise=True)
    assert len(content) > 8 * 1024 * 1024

    response = post_image(admin, ProductFactory(workspace=workspace), upload(content))

    assert_file_error(response, "8 MB")


@pytest.mark.parametrize(
    ("content", "name", "content_type"),
    [
        (image_bytes(600, 600, "GIF"), "photo.gif", "image/gif"),
        (b"definitely not an image" * 100, "photo.jpg", "image/jpeg"),
        (image_bytes(600, 600, noise=True)[:200_000], "truncated.png", "image/png"),
    ],
    ids=["gif", "not-an-image", "truncated"],
)
def test_invalid_images_are_rejected(admin, workspace, content, name, content_type):
    response = post_image(
        admin, ProductFactory(workspace=workspace), upload(content, name, content_type)
    )

    assert_file_error(response, "JPEG or PNG")


def test_decompression_bombs_are_rejected(admin, workspace, monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)

    response = post_image(admin, ProductFactory(workspace=workspace), upload(image_bytes(600, 600)))

    assert_file_error(response, "JPEG or PNG")


def test_missing_file_is_rejected(admin, workspace):
    response = admin.post(image_url(ProductFactory(workspace=workspace)), {}, format="multipart")

    assert response.status_code == 400
    assert "file" in response.json()["error"]["details"]


def test_delete_image(admin, workspace):
    product = ProductFactory(workspace=workspace, image="catalog/products/x/ab/abc.png")

    response = admin.delete(image_url(product))

    assert response.status_code == 200, response.content
    assert response.json()["image_url"] is None
    product.refresh_from_db()
    assert not product.image


def test_image_changes_queue_a_catalog_sync(admin, workspace, django_capture_on_commit_callbacks):
    MetaCatalogFactory(waba__workspace=workspace)
    product = ProductFactory(workspace=workspace)

    with django_capture_on_commit_callbacks() as callbacks:
        assert post_image(admin, product, upload(image_bytes(500, 500))).status_code == 200

    assert len(callbacks) == 1


def test_image_endpoints_need_admin_and_membership(auth_client, workspace, other_workspace):
    product = ProductFactory(workspace=workspace)
    file = upload(image_bytes(500, 500))

    assert post_image(auth_client(Role.AGENT), product, file).status_code == 403
    assert auth_client(workspace=other_workspace).delete(image_url(product)).status_code == 404
