"""Validation for media uploaded to send over WhatsApp, and safe file names for downloads.

Supported types and size caps follow Meta's Cloud API media documentation (limits set by Meta):

- image: JPEG, PNG, 5 MB
- video: MP4, 3GPP, 16 MB
- audio: AAC, AMR, MP3, MP4 audio, OGG (Opus), 16 MB
- document: plain text, PDF and Microsoft Office formats, 100 MB
- sticker: WebP, 100 KB static and 500 KB animated

``settings.WHATSAPP_MEDIA_MAX_BYTES`` can lower a cap per kind; the effective limit is the smaller
of the setting and Meta's limit. The browser-supplied MIME type is checked against the file's
leading bytes for formats with a reliable signature, so a renamed file can't pass as another type.
"""

import os
import re
import unicodedata

from django.conf import settings

KB = 1024
MB = 1024 * KB

SUPPORTED_MIME_TYPES: dict[str, str] = {
    "image/jpeg": "image",
    "image/png": "image",
    "image/webp": "sticker",
    "video/mp4": "video",
    "video/3gpp": "video",
    "audio/aac": "audio",
    "audio/amr": "audio",
    "audio/mpeg": "audio",
    "audio/mp4": "audio",
    "audio/ogg": "audio",
    "text/plain": "document",
    "application/pdf": "document",
    "application/msword": "document",
    "application/vnd.ms-excel": "document",
    "application/vnd.ms-powerpoint": "document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "document",
}

META_MAX_BYTES: dict[str, int] = {
    "image": 5 * MB,
    "video": 16 * MB,
    "audio": 16 * MB,
    "document": 100 * MB,
    "sticker": 500 * KB,
}
STATIC_STICKER_MAX_BYTES = 100 * KB

HEADER_BYTES = 64
MAX_FILE_NAME_LENGTH = 255
_UNSAFE_NAME_CHARS = re.compile(r'[\x00-\x1f\x7f"\\/<>:|?*;]')


class MediaValidationError(ValueError):
    pass


def base_mime_type(content_type: str | None) -> str:
    """``audio/ogg; codecs=opus`` -> ``audio/ogg``."""
    return (content_type or "").split(";", 1)[0].strip().lower()


def _is_ftyp(head: bytes) -> bool:
    return head[4:8] == b"ftyp"


def _signature_matches(mime_type: str, head: bytes) -> bool:
    """False only when the type has a known signature and the file doesn't carry it."""
    checks = {
        "image/jpeg": lambda: head.startswith(b"\xff\xd8\xff"),
        "image/png": lambda: head.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": lambda: head[:4] == b"RIFF" and head[8:12] == b"WEBP",
        "application/pdf": lambda: head.startswith(b"%PDF"),
        "video/mp4": lambda: _is_ftyp(head),
        "video/3gpp": lambda: _is_ftyp(head),
        "audio/mp4": lambda: _is_ftyp(head),
        "audio/ogg": lambda: head.startswith(b"OggS"),
        "audio/amr": lambda: head.startswith(b"#!AMR"),
    }
    check = checks.get(mime_type)
    return check() if check else True


def _is_animated_webp(head: bytes) -> bool:
    # Extended WebP: a VP8X chunk whose flags byte has the animation bit set.
    return head[12:16] == b"VP8X" and len(head) > 20 and bool(head[20] & 0x02)


def max_bytes(kind: str, *, animated: bool = True) -> int:
    configured = settings.WHATSAPP_MEDIA_MAX_BYTES.get(kind, META_MAX_BYTES[kind])
    limit = min(configured, META_MAX_BYTES[kind])
    if kind == "sticker" and not animated:
        limit = min(limit, STATIC_STICKER_MAX_BYTES)
    return limit


def validate_upload(upload) -> str:
    """Check an uploaded file's type and size; returns its normalised MIME type."""
    mime_type = base_mime_type(getattr(upload, "content_type", ""))
    kind = SUPPORTED_MIME_TYPES.get(mime_type)
    if kind is None:
        raise MediaValidationError(
            f"WhatsApp does not support {mime_type or 'this file type'}. Upload an image (JPEG, "
            "PNG), video (MP4, 3GPP), audio (AAC, AMR, MP3, MP4, OGG), sticker (WebP) or document "
            "(PDF, TXT, Word, Excel, PowerPoint)."
        )
    head = _read_head(upload)
    if not _signature_matches(mime_type, head):
        raise MediaValidationError(f"The file content does not match its type {mime_type}.")
    limit = max_bytes(kind, animated=kind != "sticker" or _is_animated_webp(head))
    if upload.size > limit:
        raise MediaValidationError(
            f"The {kind} is larger than WhatsApp's {_human_size(limit)} limit."
        )
    return mime_type


def _read_head(upload) -> bytes:
    position = upload.tell() if hasattr(upload, "tell") else 0
    upload.seek(0)
    head = upload.read(HEADER_BYTES)
    upload.seek(position)
    return head or b""


def _human_size(size: int) -> str:
    return f"{size // MB} MB" if size >= MB and size % MB == 0 else f"{size // KB} KB"


def safe_file_name(name: str | None, default: str = "file") -> str:
    """A display file name without paths, control characters or header-breaking characters."""
    name = unicodedata.normalize("NFC", str(name or ""))
    name = os.path.basename(name.replace("\\", "/"))
    name = _UNSAFE_NAME_CHARS.sub("_", name).strip(" .")
    if not name:
        return default
    if len(name) > MAX_FILE_NAME_LENGTH:
        stem, extension = os.path.splitext(name)
        extension = extension[:16]
        name = stem[: MAX_FILE_NAME_LENGTH - len(extension)] + extension
    return name
