import pytest

from apps.billing import entitlements
from apps.catalog import sync
from apps.catalog.factories import MetaCatalogFactory
from apps.catalog.tasks import sync_products
from apps.whatsapp.factories import PhoneNumberFactory, WhatsAppBusinessAccountFactory
from common.roles import Role

BASE = "/api/v1/catalog"
PRODUCTS = f"{BASE}/products/"
COLLECTIONS = f"{BASE}/collections/"
META_CATALOGS = f"{BASE}/meta-catalogs/"
STORE_PHONE = "+919812345678"
STORE_LINK = "https://wa.me/919812345678?text=Hi"


def detail(base: str, obj, suffix: str = "") -> str:
    return f"{base}{obj.pk}/{suffix}"


def run_sync(meta_catalog, **kwargs):
    return sync_products.apply(args=[str(meta_catalog.pk)], kwargs=kwargs)


@pytest.fixture
def admin(auth_client):
    return auth_client(Role.ADMIN)


@pytest.fixture
def frames(monkeypatch):
    """``(type, data)`` of every realtime frame the sync sends."""
    sent = []
    monkeypatch.setattr(
        sync, "broadcast", lambda workspace_id, type, data: sent.append((type, data))
    )
    return sent


@pytest.fixture
def connected(workspace, fake_graph):
    """A connected Meta catalog on a WABA with a default number, known to the fake Graph API."""
    waba = WhatsAppBusinessAccountFactory(workspace=workspace)
    fake_graph.add_waba(waba.waba_id)
    PhoneNumberFactory(
        waba=waba,
        phone_e164=STORE_PHONE,
        display_phone_number="+91 98123 45678",
        is_default=True,
    )
    meta_catalog = MetaCatalogFactory(waba=waba)
    fake_graph.add_catalog(meta_catalog.catalog_id, waba_id=waba.waba_id)
    return meta_catalog


@pytest.fixture
def no_commerce(monkeypatch):
    real = entitlements.has_feature

    def has_feature(workspace, feature):
        return feature != entitlements.COMMERCE and real(workspace, feature)

    monkeypatch.setattr(entitlements, "has_feature", has_feature)
