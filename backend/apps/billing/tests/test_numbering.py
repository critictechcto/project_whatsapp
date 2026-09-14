"""Invoice number allocation: per financial year, gap-free and safe under concurrency."""

import threading
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from django.db import connection, transaction

from apps.billing import services
from apps.billing.models import InvoiceSequence

IST = ZoneInfo("Asia/Kolkata")


@pytest.mark.django_db
def test_numbers_are_consecutive_and_restart_in_april():
    moments = [
        datetime(2026, 4, 1, 0, 0, tzinfo=IST),
        datetime(2026, 11, 5, 12, 0, tzinfo=IST),
        datetime(2027, 3, 31, 23, 59, tzinfo=IST),
        datetime(2027, 4, 1, 0, 0, tzinfo=IST),
    ]

    numbers = [services.allocate_invoice_number(moment)[0] for moment in moments]

    assert numbers == [
        "UPC/26-27/000001",
        "UPC/26-27/000002",
        "UPC/26-27/000003",
        "UPC/27-28/000001",
    ]
    assert InvoiceSequence.objects.get(financial_year="2026-27").last_serial == 3


@pytest.mark.django_db
def test_a_rolled_back_invoice_leaves_no_gap():
    at = datetime(2026, 6, 1, tzinfo=UTC)

    with pytest.raises(RuntimeError), transaction.atomic():
        services.allocate_invoice_number(at)
        raise RuntimeError("invoice creation failed")

    assert services.allocate_invoice_number(at)[0] == "UPC/26-27/000001"


@pytest.mark.django_db(transaction=True)
def test_concurrent_allocations_get_distinct_consecutive_numbers():
    at = datetime(2026, 5, 1, tzinfo=UTC)
    workers = 6
    barrier = threading.Barrier(workers)
    numbers: list[str] = []
    errors: list[Exception] = []
    lock = threading.Lock()

    def allocate():
        try:
            barrier.wait(timeout=10)
            with transaction.atomic():
                number, _ = services.allocate_invoice_number(at)
            with lock:
                numbers.append(number)
        except Exception as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=allocate) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors
    assert sorted(numbers) == [f"UPC/26-27/{serial:06d}" for serial in range(1, workers + 1)]
