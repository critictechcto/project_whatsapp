"""Background CSV contact import."""

import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from common.phone import InvalidPhoneNumber, normalize_e164, to_wa_id

from .models import MAX_IMPORT_ERRORS, ConsentEvent, Contact, ContactImport

logger = logging.getLogger(__name__)

BATCH_SIZE = 500
PHONE_ALIASES = ("phone", "phone_number", "mobile", "whatsapp", "number")
# A "processing" import older than this is treated as abandoned (worker died) and restarted.
STALE_PROCESSING_AFTER = timedelta(minutes=40)


class ImportAborted(Exception):
    """A problem with the whole file; the import is marked failed with this message."""


@dataclass
class _Row:
    line: int
    name: str = ""
    email: str = ""
    attributes: dict = field(default_factory=dict)

    def merge(self, other: "_Row") -> None:
        self.line = other.line
        self.name = other.name or self.name
        self.email = other.email or self.email
        self.attributes.update(other.attributes)


@dataclass
class _Columns:
    phone: int
    name: int | None
    email: int | None
    attributes: dict[int, str]

    @classmethod
    def from_header(cls, header: list[str]) -> "_Columns":
        keys = [cell.strip().casefold() for cell in header]
        phone = next((i for i, key in enumerate(keys) if key in PHONE_ALIASES), None)
        if phone is None:
            raise ImportAborted(
                f"No phone column found. Name one column {', '.join(PHONE_ALIASES)}."
            )
        name = keys.index("name") if "name" in keys else None
        email = keys.index("email") if "email" in keys else None
        attributes = {
            i: key
            for i, key in enumerate(keys)
            if key and i not in (phone, name, email) and key not in keys[:i]
        }
        return cls(phone=phone, name=name, email=email, attributes=attributes)


def _cell(row: list[str], index: int | None) -> str:
    return row[index].strip() if index is not None and index < len(row) else ""


class _Importer:
    def __init__(self, job: ContactImport) -> None:
        self.job = job
        self.max_rows = getattr(settings, "CONTACT_IMPORT_MAX_ROWS", 100_000)
        self.region = getattr(settings, "DEFAULT_PHONE_REGION", "IN")
        self.tag_ids = list(job.tags.values_list("pk", flat=True))
        self.opt_in = job.mark_opted_in and job.consent_attested
        self.seen: set[str] = set()

    def add_error(self, line: int | None, message: str) -> None:
        if len(self.job.errors) < MAX_IMPORT_ERRORS:
            self.job.errors.append({"row": line, "error": message})

    def run(self) -> None:
        job = self.job
        job.total_rows = job.created_count = job.updated_count = 0
        job.skipped_count = job.error_count = 0
        job.errors = []
        with job.file.open("rb") as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
            try:
                self._read(csv.reader(text))
            except UnicodeDecodeError as exc:
                raise ImportAborted("The file is not UTF-8 encoded text.") from exc
            except csv.Error as exc:
                raise ImportAborted(f"The file is not a valid CSV: {exc}") from exc
            finally:
                text.detach()

    def _read(self, reader) -> None:
        header = next(reader, None)
        if not header or not any(cell.strip() for cell in header):
            raise ImportAborted("The file is empty.")
        columns = _Columns.from_header(header)

        batch: dict[str, _Row] = {}
        for line, row in enumerate(reader, start=2):
            if not any(cell.strip() for cell in row):
                continue
            if self.job.total_rows >= self.max_rows:
                self.add_error(
                    line, f"Row limit of {self.max_rows} reached; the rest was not imported."
                )
                break
            self.job.total_rows += 1
            parsed = self._parse(line, row, columns)
            if parsed is None:
                continue
            phone, data = parsed
            if phone in batch:
                batch[phone].merge(data)
            else:
                batch[phone] = data
            if len(batch) >= BATCH_SIZE:
                self._flush(batch)
                batch = {}
        if batch:
            self._flush(batch)

    def _parse(self, line: int, row: list[str], columns: _Columns) -> tuple[str, _Row] | None:
        try:
            phone = normalize_e164(_cell(row, columns.phone), self.region)
        except InvalidPhoneNumber as exc:
            self.job.error_count += 1
            self.add_error(line, str(exc))
            return None
        email = _cell(row, columns.email)
        if email:
            try:
                validate_email(email)
            except ValidationError:
                self.job.error_count += 1
                self.add_error(line, f"'{email}' is not a valid email address.")
                return None
        attributes = {
            key: value for index, key in columns.attributes.items() if (value := _cell(row, index))
        }
        return phone, _Row(
            line=line,
            name=_cell(row, columns.name)[:255],
            email=email[:254],
            attributes=attributes,
        )

    def _flush(self, batch: dict[str, _Row]) -> None:
        job = self.job
        now = timezone.now()
        with transaction.atomic():
            existing = {
                contact.phone_e164: contact
                for contact in Contact.objects.select_for_update().filter(
                    workspace_id=job.workspace_id, phone_e164__in=list(batch)
                )
            }
            to_create, to_update = [], []
            for phone, data in batch.items():
                contact = existing.get(phone)
                if contact is None:
                    to_create.append(
                        Contact(
                            workspace_id=job.workspace_id,
                            phone_e164=phone,
                            wa_id=to_wa_id(phone),
                            name=data.name,
                            email=data.email,
                            attributes=data.attributes,
                        )
                    )
                else:
                    contact.name = data.name or contact.name
                    contact.email = data.email or contact.email
                    contact.attributes = {**(contact.attributes or {}), **data.attributes}
                    contact.updated_at = now
                    to_update.append(contact)
                    if phone not in self.seen:
                        job.updated_count += 1
            # ignore_conflicts: a webhook may create the same contact concurrently.
            Contact.objects.bulk_create(to_create, ignore_conflicts=True)
            Contact.objects.bulk_update(to_update, ["name", "email", "attributes", "updated_at"])
            job.created_count += len(to_create)

            contacts = list(
                Contact.objects.select_for_update().filter(
                    workspace_id=job.workspace_id, phone_e164__in=list(batch)
                )
            )
            if self.tag_ids:
                through = Contact.tags.through
                through.objects.bulk_create(
                    [
                        through(contact_id=contact.pk, tag_id=tag_id)
                        for contact in contacts
                        for tag_id in self.tag_ids
                    ],
                    ignore_conflicts=True,
                )
            if self.opt_in:
                self._opt_in(contacts, batch, now)
            self.seen.update(batch)
            job.save(update_fields=self._progress_fields())

    def _opt_in(self, contacts: list[Contact], batch: dict[str, _Row], now) -> None:
        job = self.job
        eligible = []
        for contact in contacts:
            status = contact.marketing_opt_in_status
            if status == Contact.OptInStatus.UNKNOWN:
                eligible.append(contact)
            elif status == Contact.OptInStatus.OPTED_OUT and contact.phone_e164 not in self.seen:
                job.skipped_count += 1
                self.add_error(
                    batch[contact.phone_e164].line,
                    "Contact has opted out of marketing; imported without opting in.",
                )
        if not eligible:
            return
        Contact.objects.filter(pk__in=[contact.pk for contact in eligible]).update(
            marketing_opt_in_status=Contact.OptInStatus.OPTED_IN,
            opted_in_at=now,
            opt_in_source=ConsentEvent.Source.IMPORT,
            updated_at=now,
        )
        evidence = (
            f"Contact import {job.pk}; consent attested by the uploader. "
            f"Opt-in source: {job.opt_in_source}"
        )
        ConsentEvent.objects.bulk_create(
            [
                ConsentEvent(
                    workspace_id=job.workspace_id,
                    contact=contact,
                    action=ConsentEvent.Action.OPT_IN,
                    source=ConsentEvent.Source.IMPORT,
                    evidence=evidence,
                    actor_id=job.created_by_id,
                    occurred_at=now,
                )
                for contact in eligible
            ]
        )

    @staticmethod
    def _progress_fields() -> list[str]:
        return [
            "total_rows",
            "created_count",
            "updated_count",
            "skipped_count",
            "error_count",
            "errors",
            "updated_at",
        ]


def _claim(import_pk) -> ContactImport | None:
    """Move a queued (or abandoned) import to processing; None if there is nothing to do."""
    with transaction.atomic():
        job = ContactImport.objects.select_for_update().filter(pk=import_pk).first()
        if job is None:
            logger.warning("Contact import %s no longer exists", import_pk)
            return None
        stale = (
            job.status == ContactImport.Status.PROCESSING
            and job.started_at is not None
            and job.started_at < timezone.now() - STALE_PROCESSING_AFTER
        )
        if job.status != ContactImport.Status.QUEUED and not stale:
            return None
        job.status = ContactImport.Status.PROCESSING
        job.started_at = timezone.now()
        job.finished_at = None
        job.save(update_fields=["status", "started_at", "finished_at", "updated_at"])
        return job


@shared_task(bind=True, name="contacts.import_csv", soft_time_limit=1800, time_limit=1860)
def import_csv(self, import_pk: str) -> None:
    """Import contacts from an uploaded CSV. Safe to run again: finished imports are skipped."""
    job = _claim(import_pk)
    if job is None:
        return
    importer = _Importer(job)
    try:
        importer.run()
    except Exception as exc:
        if isinstance(exc, ImportAborted):
            message = str(exc)
        else:
            logger.exception("Contact import %s failed", job.pk)
            message = "The import failed unexpectedly. Contacts saved so far were kept."
        job.errors = [*job.errors[: MAX_IMPORT_ERRORS - 1], {"row": None, "error": message}]
        job.status = ContactImport.Status.FAILED
    else:
        job.status = ContactImport.Status.COMPLETED
    job.finished_at = timezone.now()
    job.save(update_fields=[*_Importer._progress_fields(), "status", "finished_at"])
