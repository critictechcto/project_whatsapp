"""Product images: validated on the decoded image, stored under a content-hashed name.

Meta fetches ``image_link`` itself, so the stored file must be a real JPEG or PNG of at least
500x500 px. The client's content type and file name are never trusted. A new image gets a new
name (``catalog/products/<workspace>/<aa>/<sha256>.<ext>``), so Meta and WhatsApp clients never
show a stale cached image. Old files are kept: past order items snapshot their image URL.
"""

import hashlib
import warnings

from PIL import Image, UnidentifiedImageError
from rest_framework import serializers

from .models import Product

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MIN_IMAGE_SIDE = 500
SUFFIXES = {"JPEG": ".jpg", "PNG": ".png"}
INVALID_IMAGE = "Upload a JPEG or PNG image."


def _invalid(message: str) -> serializers.ValidationError:
    return serializers.ValidationError({"file": [message]})


def validate_image(upload) -> str:
    """Decode ``upload`` fully and return its file suffix (``.jpg`` or ``.png``).

    Raises a 400 ``invalid`` error on ``file`` when it is too large, not a JPEG/PNG, truncated,
    a decompression bomb or smaller than 500x500 px.
    """
    if upload.size > MAX_IMAGE_BYTES:
        raise _invalid("The image is larger than the 8 MB limit.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            upload.seek(0)
            with Image.open(upload) as image:
                image_format = image.format
                if image_format not in SUFFIXES:
                    raise _invalid(INVALID_IMAGE)
                width, height = image.size
                if width < MIN_IMAGE_SIDE or height < MIN_IMAGE_SIDE:
                    raise _invalid(
                        f"The image must be at least {MIN_IMAGE_SIDE}x{MIN_IMAGE_SIDE} pixels; "
                        f"this one is {width}x{height}."
                    )
                image.load()  # a truncated or corrupt file fails here
    except serializers.ValidationError:
        raise
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        SyntaxError,
        ValueError,
    ):
        raise _invalid(INVALID_IMAGE) from None
    finally:
        upload.seek(0)
    return SUFFIXES[image_format]


def content_sha256(upload) -> str:
    hasher = hashlib.sha256()
    upload.seek(0)
    for chunk in upload.chunks():
        hasher.update(chunk)
    upload.seek(0)
    return hasher.hexdigest()


def store_image(product: Product, upload, suffix: str) -> str:
    """Save ``upload`` through the image field's storage and return the stored name."""
    digest = content_sha256(upload)
    name = f"catalog/products/{product.workspace_id}/{digest[:2]}/{digest}{suffix}"
    storage = product.image.storage
    if storage.exists(name):
        return name
    upload.seek(0)
    return storage.save(name, upload)
