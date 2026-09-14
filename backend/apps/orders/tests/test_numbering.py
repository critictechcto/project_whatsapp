"""Order numbers: ``<prefix>-<n>`` from 1001, per workspace, gap-free and safe under concurrency."""

import threading

import pytest
from django.db import connection, transaction

from apps.orders import services
from apps.orders.factories import StoreSettingsFactory
from apps.orders.models import OrderCounter
from apps.tenants.factories import WorkspaceFactory


@pytest.mark.django_db
def test_numbers_start_at_1001_and_are_per_workspace(workspace, other_workspace):
    StoreSettingsFactory(workspace=workspace, order_prefix="SS")
    StoreSettingsFactory(workspace=other_workspace, order_prefix="CHA")

    assert services.next_order_number(workspace) == "SS-1001"
    assert services.next_order_number(workspace) == "SS-1002"
    assert services.next_order_number(other_workspace) == "CHA-1001"
    assert OrderCounter.objects.get(workspace=workspace).last_value == 1002


@pytest.mark.django_db
def test_first_number_uses_the_prefix_derived_from_the_workspace_name():
    workspace = WorkspaceFactory(name="Sharma Sweets")

    assert services.next_order_number(workspace) == "SS-1001"


@pytest.mark.django_db
def test_a_rolled_back_order_leaves_no_gap(workspace):
    StoreSettingsFactory(workspace=workspace, order_prefix="SS")

    with pytest.raises(RuntimeError), transaction.atomic():
        services.next_order_number(workspace)
        raise RuntimeError("checkout failed")

    assert services.next_order_number(workspace) == "SS-1001"


@pytest.mark.django_db(transaction=True)
def test_concurrent_allocations_get_distinct_consecutive_numbers():
    workspace = WorkspaceFactory()
    StoreSettingsFactory(workspace=workspace, order_prefix="SS")
    workers = 6
    barrier = threading.Barrier(workers)
    numbers: list[str] = []
    errors: list[Exception] = []
    lock = threading.Lock()

    def allocate():
        try:
            barrier.wait(timeout=10)
            with transaction.atomic():
                number = services.next_order_number(workspace)
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
    assert sorted(numbers) == [f"SS-{1001 + index}" for index in range(workers)]
