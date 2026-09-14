import factory

from apps.tenants.factories import WorkspaceFactory
from apps.whatsapp.factories import WhatsAppBusinessAccountFactory

from .models import CatalogSyncBatch, Collection, MetaCatalog, MetaCatalogPhoneSetting, Product


class CollectionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Collection

    workspace = factory.SubFactory(WorkspaceFactory)
    name = factory.Sequence(lambda n: f"Collection {n}")
    description = "Freshly made every day"
    position = factory.Sequence(lambda n: n)


class ProductFactory(factory.django.DjangoModelFactory):
    """An active, in-stock product with untracked stock at ₹249.00."""

    class Meta:
        model = Product

    workspace = factory.SubFactory(WorkspaceFactory)
    sku = factory.Sequence(lambda n: f"SKU-{n:05d}")
    name = factory.Sequence(lambda n: f"Kaju Katli {n}")
    description = "Made with pure ghee."
    price_paise = 24900
    position = factory.Sequence(lambda n: n)


class MetaCatalogFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MetaCatalog

    waba = factory.SubFactory(WhatsAppBusinessAccountFactory)
    workspace = factory.SelfAttribute("waba.workspace")
    catalog_id = factory.Sequence(lambda n: f"30{n:013d}")
    catalog_name = factory.Sequence(lambda n: f"Catalog {n}")
    business_id = factory.Sequence(lambda n: f"40{n:013d}")
    status = MetaCatalog.Status.CONNECTED


class MetaCatalogPhoneSettingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MetaCatalogPhoneSetting

    meta_catalog = factory.SubFactory(MetaCatalogFactory)
    workspace = factory.SelfAttribute("meta_catalog.workspace")
    phone_number = factory.SubFactory(
        "apps.whatsapp.factories.PhoneNumberFactory",
        waba=factory.SelfAttribute("..meta_catalog.waba"),
    )
    is_cart_enabled = True
    is_catalog_visible = True


class CatalogSyncBatchFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CatalogSyncBatch

    meta_catalog = factory.SubFactory(MetaCatalogFactory)
    workspace = factory.SelfAttribute("meta_catalog.workspace")
    handle = factory.Sequence(lambda n: f"handle-{n}")
    status = CatalogSyncBatch.Status.PENDING
