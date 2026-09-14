"""Meta catalog sync: batching, deletes, the 80014 backoff, batch and review polling."""

from datetime import timedelta
from unittest import mock

import pytest
from celery.exceptions import Retry
from django.utils import timezone

from apps.catalog import services, sync
from apps.catalog.factories import CatalogSyncBatchFactory, ProductFactory
from apps.catalog.models import CatalogSyncBatch, MetaCatalog, Product
from apps.catalog.tasks import MAX_SYNC_RETRIES, poll_sync_status, sync_products
from apps.whatsapp.client.errors import GraphAPIError, GraphPermissionError
from apps.whatsapp.models import PhoneNumber

from .conftest import STORE_LINK, run_sync

pytestmark = pytest.mark.django_db

RATE_LIMITED = GraphAPIError("Too many catalog batch requests", http_status=400, code=80014)


def image(sku: str) -> str:
    return f"catalog/products/ws/ab/{sku}.jpg"


def frame(meta_catalog, status: str) -> tuple[str, dict]:
    return ("catalog.sync", {"meta_catalog_id": str(meta_catalog.pk), "status": status})


def sent_requests(fake_graph) -> list[list[dict]]:
    return [call.kwargs["requests"] for call in fake_graph.calls_to("batch_catalog_items")]


# --- Sending ----------------------------------------------------------------------------------


def test_sync_upserts_active_products_with_images(connected, workspace, fake_graph, frames):
    kaju = ProductFactory(
        workspace=workspace,
        sku="KAJU-1",
        name="Kaju Katli",
        description="",
        price_paise=64000,
        sale_price_paise=59950,
        image=image("KAJU-1"),
    )
    sold_out = ProductFactory(workspace=workspace, sku="SAMOSA-6", stock_qty=0, image=image("S"))
    no_image = ProductFactory(workspace=workspace, sku="LADDU-1")
    ProductFactory(workspace=workspace, sku="HIDDEN-1", is_active=False, image=image("H"))

    run_sync(connected)

    [requests] = sent_requests(fake_graph)
    by_id = {request["data"]["id"]: request for request in requests}
    assert set(by_id) == {"KAJU-1", "SAMOSA-6"}
    assert by_id["KAJU-1"] == {
        "method": "UPDATE",
        "data": {
            "id": "KAJU-1",
            "title": "Kaju Katli",
            "description": "Kaju Katli",
            "availability": "in stock",
            "condition": "new",
            "price": "640.00 INR",
            "sale_price": "599.50 INR",
            "link": STORE_LINK,
            "image_link": f"https://media.testserver/{image('KAJU-1')}",
            "brand": workspace.name,
        },
    }
    assert by_id["SAMOSA-6"]["data"]["availability"] == "out of stock"
    assert fake_graph.calls_to("batch_catalog_items")[0].access_token == connected.waba.access_token

    batch = CatalogSyncBatch.objects.get()
    assert batch.status == "pending" and batch.handle
    assert sorted(batch.retailer_ids) == ["KAJU-1", "SAMOSA-6"]
    for product, status in ((kaju, "pending"), (sold_out, "pending"), (no_image, "not_synced")):
        product.refresh_from_db()
        assert product.meta_sync_status == status
    connected.refresh_from_db()
    assert connected.last_synced_at is not None
    assert frames == [frame(connected, "pending")]


def test_sync_only_sends_products_changed_since_the_last_run(connected, workspace, fake_graph):
    kaju = ProductFactory(workspace=workspace, sku="KAJU-1", image=image("K"))
    ProductFactory(workspace=workspace, sku="BARFI-1", image=image("B"))
    run_sync(connected)
    connected.refresh_from_db()

    run_sync(connected)
    assert len(sent_requests(fake_graph)) == 1

    kaju.name = "Kaju Katli Special"
    kaju.save()
    run_sync(connected)
    assert [request["data"]["id"] for request in sent_requests(fake_graph)[-1]] == ["KAJU-1"]

    run_sync(connected, full=True)
    assert len(sent_requests(fake_graph)[-1]) == 2


def test_sync_deletes_products_that_left_the_catalog(connected, workspace, fake_graph, frames):
    connected.last_synced_at = timezone.now() - timedelta(hours=1)
    connected.save()
    hidden = ProductFactory(
        workspace=workspace,
        sku="HIDDEN-1",
        is_active=False,
        image=image("H"),
        meta_sync_status="synced",
        meta_product_id="600001",
    )
    ProductFactory(workspace=workspace, sku="NEVER-1", image="")  # never reached Meta

    run_sync(connected, delete_retailer_ids=["GONE-1"])

    [requests] = sent_requests(fake_graph)
    assert requests == [
        {"method": "DELETE", "data": {"id": "GONE-1"}},
        {"method": "DELETE", "data": {"id": "HIDDEN-1"}},
    ]

    poll_sync_status.apply()

    hidden.refresh_from_db()
    assert (hidden.meta_sync_status, hidden.meta_product_id) == ("not_synced", "")
    assert frames[-1] == frame(connected, "synced")


def test_a_reused_sku_is_not_deleted(connected, workspace, fake_graph):
    ProductFactory(workspace=workspace, sku="KAJU-1", image=image("K"))

    run_sync(connected, delete_retailer_ids=["KAJU-1"])

    [requests] = sent_requests(fake_graph)
    assert [request["method"] for request in requests] == ["UPDATE"]


def test_sync_splits_large_catalogs_into_batches(connected, workspace, fake_graph, monkeypatch):
    monkeypatch.setattr(sync, "BATCH_SIZE", 2)
    for index in range(5):
        ProductFactory(workspace=workspace, sku=f"SKU-{index}", image=image(str(index)))

    run_sync(connected)

    assert [len(requests) for requests in sent_requests(fake_graph)] == [2, 2, 1]
    assert CatalogSyncBatch.objects.count() == 3


def test_meta_validation_errors_fail_those_products(connected, workspace, fake_graph, monkeypatch):
    good = ProductFactory(workspace=workspace, sku="GOOD-1", image=image("G"))
    bad = ProductFactory(workspace=workspace, sku="BAD-1", image=image("B"))
    real = fake_graph.batch_catalog_items

    def with_validation(catalog_id, requests):
        response = real(catalog_id, requests)
        response["validation_status"] = [
            {"retailer_id": "BAD-1", "errors": [{"message": "Price is invalid"}]}
        ]
        return response

    monkeypatch.setattr(fake_graph, "batch_catalog_items", with_validation)

    run_sync(connected)

    good.refresh_from_db()
    bad.refresh_from_db()
    assert good.meta_sync_status == "pending"
    assert (bad.meta_sync_status, bad.meta_sync_error) == ("failed", "Price is invalid")


def test_sync_without_a_number_is_blocked(connected, workspace, fake_graph, frames):
    PhoneNumber.objects.filter(waba=connected.waba).delete()
    ProductFactory(workspace=workspace, image=image("K"))

    run_sync(connected)

    assert fake_graph.calls_to("batch_catalog_items") == []
    connected.refresh_from_db()
    assert connected.last_sync_error.startswith("Add a WhatsApp number")
    assert frames == [frame(connected, "failed")]


def test_sync_skips_catalogs_that_are_not_connected(connected, workspace, fake_graph):
    connected.status = MetaCatalog.Status.PERMISSIONS_MISSING
    connected.save()
    ProductFactory(workspace=workspace, image=image("K"))

    run_sync(connected)

    assert fake_graph.calls == []


# --- Rate limits and failures -----------------------------------------------------------------


def test_rate_limit_backs_off(connected, workspace, fake_graph):
    ProductFactory(workspace=workspace, image=image("K"))
    fake_graph.fail("batch_catalog_items", RATE_LIMITED)

    with mock.patch("celery.app.task.Task.retry", side_effect=Retry()) as retry:
        result = sync_products.apply(args=[str(connected.pk)], throw=False)

    assert result.state == "RETRY"
    assert retry.call_args.kwargs["countdown"] == 60
    assert retry.call_args.kwargs["exc"] is RATE_LIMITED
    assert not CatalogSyncBatch.objects.exists()
    connected.refresh_from_db()
    assert connected.last_synced_at is None


def test_rate_limit_retry_sends_the_batch(connected, workspace, fake_graph):
    product = ProductFactory(workspace=workspace, image=image("K"))
    fake_graph.fail("batch_catalog_items", RATE_LIMITED)

    sync_products.apply(args=[str(connected.pk)], throw=False)

    assert len(fake_graph.calls_to("batch_catalog_items")) == 2
    assert CatalogSyncBatch.objects.count() == 1
    product.refresh_from_db()
    assert product.meta_sync_status == "pending"


def test_rate_limit_gives_up_after_the_last_retry(connected, workspace, fake_graph, frames):
    ProductFactory(workspace=workspace, image=image("K"))
    fake_graph.fail("batch_catalog_items", RATE_LIMITED)

    sync_products.apply(args=[str(connected.pk)], retries=MAX_SYNC_RETRIES, throw=False)

    connected.refresh_from_db()
    assert connected.last_sync_error == "Too many catalog batch requests"
    assert connected.status == "connected"
    assert frames == [frame(connected, "failed")]


def test_permission_errors_mark_the_catalog(connected, workspace, fake_graph, frames):
    ProductFactory(workspace=workspace, image=image("K"))
    fake_graph.fail("batch_catalog_items", GraphPermissionError("No permission", code=10))

    run_sync(connected)

    connected.refresh_from_db()
    assert connected.status == "permissions_missing"
    assert frames == [frame(connected, "failed")]


# --- Debounce ---------------------------------------------------------------------------------


def test_queue_sync_is_debounced_per_catalog(
    connected, workspace, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks() as callbacks:
        sync.queue_sync(workspace.pk)
        sync.queue_sync(workspace.pk)

    assert len(callbacks) == 1

    run_sync(connected)  # the run clears the debounce key
    with django_capture_on_commit_callbacks() as callbacks:
        sync.queue_sync(workspace.pk)
    assert len(callbacks) == 1


def test_stock_selling_out_or_returning_queues_a_sync(
    connected, workspace, django_capture_on_commit_callbacks
):
    product = ProductFactory(workspace=workspace, stock_qty=5)

    with django_capture_on_commit_callbacks() as callbacks:
        services.reserve_stock(workspace, [(product.pk, 2)])
    assert callbacks == []

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        services.reserve_stock(workspace, [(product.pk, 3)])
    assert len(callbacks) == 1

    with django_capture_on_commit_callbacks() as callbacks:
        services.release_stock(workspace, [(product.pk, 1)])
    assert len(callbacks) == 1


# --- Polling ----------------------------------------------------------------------------------


def test_poll_finishes_batches_and_copies_reviews(connected, workspace, fake_graph, frames):
    product = ProductFactory(workspace=workspace, sku="LADDU-1", image=image("L"))
    run_sync(connected)
    fake_graph.set_product_review(connected.catalog_id, "LADDU-1", "rejected", ["IMAGE_QUALITY"])

    poll_sync_status.apply()

    batch = CatalogSyncBatch.objects.get()
    assert batch.status == "finished" and batch.finished_at
    product.refresh_from_db()
    assert product.meta_sync_status == "synced"
    assert product.meta_synced_at is not None
    assert product.meta_review_status == "rejected"
    assert product.meta_rejection_reasons == ["IMAGE_QUALITY"]
    assert product.meta_product_id
    assert frames[-1] == frame(connected, "synced")


def test_poll_fails_products_meta_reported(connected, workspace, fake_graph, frames):
    good = ProductFactory(workspace=workspace, sku="GOOD-1", image=image("G"))
    bad = ProductFactory(workspace=workspace, sku="BAD-1", image=image("B"))
    run_sync(connected)
    handle = CatalogSyncBatch.objects.get().handle
    fake_graph.catalog_batches[handle]["errors"] = [
        {"line": 2, "id": "BAD-1", "message": "Image is too small"}
    ]

    poll_sync_status.apply()

    good.refresh_from_db()
    bad.refresh_from_db()
    assert good.meta_sync_status == "synced"
    assert (bad.meta_sync_status, bad.meta_sync_error) == ("failed", "Image is too small")
    connected.refresh_from_db()
    assert connected.last_sync_error == "1 product(s) could not be synced to Meta."
    assert frames[-1] == frame(connected, "failed")


def test_poll_waits_for_batches_in_progress(connected, workspace, fake_graph, frames):
    product = ProductFactory(workspace=workspace, image=image("K"))
    run_sync(connected)
    batch = CatalogSyncBatch.objects.get()
    fake_graph.catalog_batches[batch.handle]["status"] = "in_progress"
    frames.clear()

    poll_sync_status.apply()

    batch.refresh_from_db()
    assert batch.status == "pending" and batch.last_checked_at
    product.refresh_from_db()
    assert product.meta_sync_status == "pending"
    assert frames == []


def test_poll_gives_up_on_stale_batches(connected, workspace, fake_graph):
    product = ProductFactory(workspace=workspace, image=image("K"))
    run_sync(connected)
    batch = CatalogSyncBatch.objects.get()
    fake_graph.catalog_batches[batch.handle]["status"] = "in_progress"
    CatalogSyncBatch.objects.filter(pk=batch.pk).update(
        created_at=timezone.now() - timedelta(days=2)
    )

    poll_sync_status.apply()

    batch.refresh_from_db()
    product.refresh_from_db()
    assert batch.status == "failed"
    assert product.meta_sync_status == "failed"


def test_poll_refreshes_reviews_of_products_under_review(connected, workspace, fake_graph):
    product = ProductFactory(
        workspace=workspace, sku="KAJU-1", meta_sync_status="synced", meta_review_status="pending"
    )
    fake_graph.catalog_products[connected.catalog_id]["KAJU-1"] = {
        "id": "600009",
        "retailer_id": "KAJU-1",
        "review_status": "approved",
        "review_rejection_reasons": [],
    }

    poll_sync_status.apply()
    poll_sync_status.apply()  # throttled: Meta is asked once

    product.refresh_from_db()
    assert (product.meta_review_status, product.meta_product_id) == ("approved", "600009")
    assert len(fake_graph.calls_to("list_catalog_products")) == 1


def test_poll_without_pending_work_calls_nothing(connected, workspace, fake_graph):
    ProductFactory(workspace=workspace)
    CatalogSyncBatchFactory(meta_catalog=connected, status="finished")

    poll_sync_status.apply()

    assert fake_graph.calls == []


def test_products_counts_follow_sync(connected, workspace, fake_graph):
    ProductFactory(workspace=workspace, image=image("K"))
    run_sync(connected)
    poll_sync_status.apply()

    counts = services.meta_catalog_product_counts(connected)

    assert counts["synced"] == 1
    assert counts["pending"] == 0
    assert Product.objects.get().meta_review_status == "pending"
