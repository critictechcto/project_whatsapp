import factory

from apps.contacts.factories import ContactFactory
from apps.tenants.factories import WorkspaceFactory
from apps.whatsapp.factories import PhoneNumberFactory

from .models import Order, OrderEvent, OrderItem, ShopperAddress, StoreSettings


def sample_address() -> dict:
    return {
        "name": "Asha Verma",
        "phone_e164": "+919876543210",
        "line1": "12, MG Road",
        "line2": "",
        "landmark": "Near City Mall",
        "city": "Pune",
        "state": "Maharashtra",
        "pincode": "411001",
        "country": "IN",
    }


class StoreSettingsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StoreSettings
        django_get_or_create = ("workspace",)

    workspace = factory.SubFactory(WorkspaceFactory)
    store_name = factory.LazyAttribute(lambda o: o.workspace.name[:60])
    order_prefix = "SS"


class OrderFactory(factory.django.DjangoModelFactory):
    """A confirmed, paid online order of ₹498.00 (no items; add ``OrderItemFactory`` rows).

    Contact and phone number are created in the order's workspace.
    """

    class Meta:
        model = Order

    workspace = factory.SubFactory(WorkspaceFactory)
    contact = factory.SubFactory(ContactFactory, workspace=factory.SelfAttribute("..workspace"))
    phone_number = factory.SubFactory(
        PhoneNumberFactory, waba__workspace=factory.SelfAttribute("...workspace")
    )
    number = factory.Sequence(lambda n: f"SS-{1001 + n}")
    status = Order.Status.CONFIRMED
    payment_status = Order.PaymentStatus.PAID
    payment_method = Order.PaymentMethod.ONLINE
    source = Order.Source.BOT
    item_count = 2
    subtotal_paise = 49800
    total_paise = 49800
    address = factory.LazyFunction(sample_address)


class OrderItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OrderItem

    order = factory.SubFactory(OrderFactory)
    workspace = factory.SelfAttribute("order.workspace")
    sku = factory.Sequence(lambda n: f"SKU-{n:05d}")
    name = "Kaju Katli 250 g"
    unit_price_paise = 24900
    quantity = 2
    line_total_paise = factory.LazyAttribute(lambda o: o.unit_price_paise * o.quantity)


class OrderEventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OrderEvent

    order = factory.SubFactory(OrderFactory)
    workspace = factory.SelfAttribute("order.workspace")
    type = OrderEvent.Type.CREATED
    actor = OrderEvent.Actor.BUYER


class ShopperAddressFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ShopperAddress

    workspace = factory.SubFactory(WorkspaceFactory)
    contact = factory.SubFactory(ContactFactory, workspace=factory.SelfAttribute("..workspace"))
    address = factory.LazyFunction(sample_address)
