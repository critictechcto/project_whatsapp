"""Media storage: local disk in development, DigitalOcean Spaces (S3-compatible) in production.

The API, Celery worker and beat run in separate containers with ephemeral disks, so uploads
must live in shared object storage (``MEDIA_STORAGE=s3``). Two storages share one bucket:

- ``default`` (:class:`PrivateMediaStorage`): contact CSV imports and inbox media. Objects are
  private; ``url()`` returns a signed URL that expires after ``AWS_QUERYSTRING_EXPIRE`` seconds.
- ``public_media`` (:class:`PublicMediaStorage`): product images, which Meta and WhatsApp
  clients fetch without auth. Objects are public-read; ``url()`` uses ``PUBLIC_MEDIA_BASE_URL``
  (a CDN) when set, else the bucket URL.

Code that reads an uploaded file must go through the storage (``field.open()`` or
``storage.open()``), never a local path: remote storages have no ``path()``.
"""

from urllib.parse import quote

from django.conf import settings
from django.core.files.storage import InvalidStorageError, default_storage, storages
from storages.backends.s3 import S3Storage

PUBLIC_MEDIA_ALIAS = "public_media"


class PrivateMediaStorage(S3Storage):
    """Private objects served through short-lived signed URLs."""

    default_acl = "private"
    querystring_auth = True
    # A CDN host cannot serve signed URLs for private objects, so it is never used here.
    custom_domain = None
    # Upload paths such as ``contact_imports/%Y/%m/`` repeat file names: never overwrite.
    file_overwrite = False


class PublicMediaStorage(S3Storage):
    """Public-read objects with stable, unsigned URLs (product images)."""

    default_acl = "public-read"
    querystring_auth = False
    # Names are content-hashed, so the same name always holds the same bytes.
    file_overwrite = True
    object_parameters = {"CacheControl": "public, max-age=31536000, immutable"}

    def url(self, name, parameters=None, expire=None, http_method=None):
        base = getattr(settings, "PUBLIC_MEDIA_BASE_URL", "")
        if base:
            return f"{base.rstrip('/')}/{quote(name.replace(chr(92), '/').lstrip('/'), safe='/')}"
        return super().url(name, parameters=parameters, expire=expire, http_method=http_method)


def public_media_storage():
    """Storage for files anyone may fetch (product images); the default storage when no
    ``public_media`` storage is configured (local development and tests)."""
    try:
        return storages[PUBLIC_MEDIA_ALIAS]
    except InvalidStorageError:
        return default_storage
