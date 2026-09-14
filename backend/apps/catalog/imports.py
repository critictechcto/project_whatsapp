"""Product CSV import (docs/contracts/wave-3-commerce.md, ``ProductImportResult``).

The import runs inside the request (the file is at most 2 MB and 5,000 rows) and upserts by SKU:

- Columns (case-insensitive, any order, unknown ones ignored): ``sku`` (required), ``name``,
  ``description``, ``price`` and ``sale_price`` (rupees, e.g. ``249`` or ``249.50``),
  ``collection`` (by name, created when missing), ``stock_qty``, ``max_qty_per_order``,
  ``availability`` (``in_stock``/``out_of_stock``) and ``is_active`` (``true``/``false``).
- New products need ``name`` and ``price``. For existing products an empty cell keeps the
  current value.
- A bad row is skipped with an error (``row`` counts the header as row 1); a problem with the
  whole file raises :class:`ImportRejected` and nothing is imported.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from .models import MAX_QTY_PER_ORDER, MIN_PRICE_PAISE, Collection, Product

MAX_IMPORT_BYTES = 2 * 1024 * 1024
MAX_IMPORT_ROWS = 5000
MAX_IMPORT_ERRORS = 500
MAX_INT = 2_147_483_647
BULK_BATCH_SIZE = 500

COLUMNS = (
    "sku",
    "name",
    "description",
    "price",
    "sale_price",
    "collection",
    "stock_qty",
    "max_qty_per_order",
    "availability",
    "is_active",
)
SKU_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
TRUE_VALUES = frozenset({"true", "yes", "1"})
FALSE_VALUES = frozenset({"false", "no", "0"})
AVAILABILITIES = frozenset(Product.Availability.values)
UPDATE_FIELDS = (
    "name",
    "description",
    "price_paise",
    "sale_price_paise",
    "collection",
    "stock_qty",
    "max_qty_per_order",
    "availability",
    "is_active",
    "updated_at",
)


class ImportRejected(ValueError):
    """The whole file can't be imported; the message is shown on ``file``."""


class RowError(ValueError):
    pass


@dataclass
class ImportResult:
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    errors: list[dict] = field(default_factory=list)

    def skip(self, row: int, sku: str, reason: str) -> None:
        self.skipped_count += 1
        if len(self.errors) < MAX_IMPORT_ERRORS:
            self.errors.append({"row": row, "sku": sku, "reason": reason})


def _read(upload) -> tuple[dict[str, int], list[tuple[int, list[str]]]]:
    if upload.size > MAX_IMPORT_BYTES:
        raise ImportRejected("The file is larger than the 2 MB limit.")
    raw = upload.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportRejected("The file is not UTF-8 encoded text.") from None
    try:
        reader = csv.reader(io.StringIO(text, newline=""))
        header = next(reader, None)
        if not header or not any(cell.strip() for cell in header):
            raise ImportRejected("The file is empty.")
        keys = [cell.strip().casefold() for cell in header]
        if "sku" not in keys:
            raise ImportRejected("No sku column found. Name one column sku.")
        columns = {name: keys.index(name) for name in COLUMNS if name in keys}
        rows = []
        for line, row in enumerate(reader, start=2):
            if not any(cell.strip() for cell in row):
                continue
            if len(rows) >= MAX_IMPORT_ROWS:
                raise ImportRejected(f"The file has more than {MAX_IMPORT_ROWS:,} rows.")
            rows.append((line, row))
    except csv.Error as exc:
        raise ImportRejected(f"The file is not a valid CSV: {exc}") from None
    if not rows:
        raise ImportRejected("The file has no product rows.")
    return columns, rows


def _cell(row: list[str], columns: dict[str, int], name: str) -> str:
    index = columns.get(name)
    return row[index].strip() if index is not None and index < len(row) else ""


def _paise(value: str, column: str) -> int:
    cleaned = value.replace(",", "").removeprefix("₹").strip()
    message = f"{column} must be a rupee amount such as 249 or 249.50."
    try:
        amount = Decimal(cleaned)
        if not amount.is_finite() or amount != amount.quantize(Decimal("0.01")):
            raise RowError(message)
    except InvalidOperation:
        raise RowError(message) from None
    paise = int(amount * 100)
    if paise < MIN_PRICE_PAISE or paise > MAX_INT:
        raise RowError(f"{column} must be at least ₹{MIN_PRICE_PAISE // 100}.")
    return paise


def _integer(value: str, column: str, *, minimum: int, maximum: int) -> int:
    if not re.fullmatch(r"-?\d{1,10}", value):
        raise RowError(f"{column} must be a whole number.")
    number = int(value)
    if number < minimum or number > maximum:
        raise RowError(f"{column} must be between {minimum} and {maximum}.")
    return number


def _parse_row(row: list[str], columns: dict[str, int]) -> dict:
    """The non-empty cells of a row as Product field values."""
    fields: dict = {}
    if name := _cell(row, columns, "name"):
        if len(name) > 200:
            raise RowError("name must be at most 200 characters.")
        fields["name"] = name
    if description := _cell(row, columns, "description"):
        if len(description) > 1000:
            raise RowError("description must be at most 1000 characters.")
        fields["description"] = description
    if price := _cell(row, columns, "price"):
        fields["price_paise"] = _paise(price, "price")
    if sale_price := _cell(row, columns, "sale_price"):
        fields["sale_price_paise"] = _paise(sale_price, "sale_price")
    if collection := _cell(row, columns, "collection"):
        if len(collection) > 24:
            raise RowError("collection must be at most 24 characters.")
        fields["collection"] = collection
    if stock := _cell(row, columns, "stock_qty"):
        fields["stock_qty"] = _integer(stock, "stock_qty", minimum=0, maximum=MAX_INT)
    if max_qty := _cell(row, columns, "max_qty_per_order"):
        fields["max_qty_per_order"] = _integer(
            max_qty, "max_qty_per_order", minimum=1, maximum=MAX_QTY_PER_ORDER
        )
    if availability := _cell(row, columns, "availability").lower():
        if availability not in AVAILABILITIES:
            raise RowError("availability must be in_stock or out_of_stock.")
        fields["availability"] = availability
    if is_active := _cell(row, columns, "is_active").lower():
        if is_active not in TRUE_VALUES | FALSE_VALUES:
            raise RowError("is_active must be true or false.")
        fields["is_active"] = is_active in TRUE_VALUES
    return fields


def _next_position(queryset) -> int:
    top = queryset.aggregate(top=Max("position"))["top"]
    return 0 if top is None else top + 1


def import_products(workspace, upload) -> ImportResult:
    """Upsert products from a CSV upload; see the module docstring for the format."""
    columns, rows = _read(upload)
    result = ImportResult()

    parsed: list[tuple[int, str, dict]] = []
    seen: set[str] = set()
    for line, row in rows:
        sku = _cell(row, columns, "sku")
        try:
            if not sku:
                raise RowError("sku is required.")
            if not SKU_RE.fullmatch(sku):
                raise RowError("sku must be 1-100 letters, digits, underscores or hyphens.")
            if sku in seen:
                raise RowError("This SKU appears earlier in the file.")
            fields = _parse_row(row, columns)
        except RowError as exc:
            result.skip(line, sku[:100], str(exc))
            continue
        seen.add(sku)
        parsed.append((line, sku, fields))

    try:
        with transaction.atomic():
            _write(workspace, parsed, result)
    except IntegrityError:
        raise ImportRejected(
            "The catalog changed while importing. Nothing was imported; try again."
        ) from None

    result.errors.sort(key=lambda error: error["row"])
    if result.created_count or result.updated_count:
        from .sync import queue_sync

        queue_sync(workspace.pk)
    return result


def _write(workspace, parsed: list[tuple[int, str, dict]], result: ImportResult) -> None:
    now = timezone.now()
    products = Product.objects.filter(workspace=workspace)
    existing = {
        product.sku: product
        for product in products.select_for_update().filter(sku__in=[sku for _, sku, _ in parsed])
    }
    collections = {
        collection.name.casefold(): collection
        for collection in Collection.objects.filter(workspace=workspace)
    }
    next_product_position = _next_position(products)
    next_collection_position = _next_position(Collection.objects.filter(workspace=workspace))

    to_create: list[Product] = []
    to_update: list[Product] = []
    for line, sku, fields in parsed:
        product = existing.get(sku)
        if product is None:
            if "name" not in fields or "price_paise" not in fields:
                result.skip(line, sku, "New products need a name and a price.")
                continue
            product = Product(workspace=workspace, sku=sku, position=next_product_position)
        price = fields.get("price_paise", product.price_paise)
        sale_price = fields.get("sale_price_paise", product.sale_price_paise)
        if sale_price is not None and sale_price >= price:
            result.skip(line, sku, "sale_price must be lower than price.")
            continue

        collection_name = fields.pop("collection", None)
        for name, value in fields.items():
            setattr(product, name, value)
        if collection_name is not None:
            collection = collections.get(collection_name.casefold())
            if collection is None:
                collection = Collection.objects.create(
                    workspace=workspace, name=collection_name, position=next_collection_position
                )
                next_collection_position += 1
                collections[collection_name.casefold()] = collection
            product.collection = collection

        if product._state.adding:
            next_product_position += 1
            to_create.append(product)
        else:
            product.updated_at = now
            to_update.append(product)

    Product.objects.bulk_create(to_create, batch_size=BULK_BATCH_SIZE)
    Product.objects.bulk_update(to_update, UPDATE_FIELDS, batch_size=BULK_BATCH_SIZE)
    result.created_count = len(to_create)
    result.updated_count = len(to_update)
