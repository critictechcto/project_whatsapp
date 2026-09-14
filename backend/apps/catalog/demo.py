"""Demo catalog for ``manage.py seed_demo``: "Sharma Sweets" with 3 collections and 12 products.

Rows are keyed on the collection name and the SKU and never overwritten, so running the seeder
again changes nothing (and keeps edits made in the dashboard). Products have no images, so they
stay ``not_synced`` for native catalog mode; bot mode works without images.
"""

from .models import Collection, Product

IN_STOCK = Product.Availability.IN_STOCK
OUT_OF_STOCK = Product.Availability.OUT_OF_STOCK

DEMO_COLLECTIONS = [
    ("Mithai", "Fresh sweets made every morning in pure desi ghee"),
    ("Namkeen", "Crunchy savoury snacks for chai time"),
    ("Gift boxes", "Assorted boxes for Diwali, Rakhi and weddings"),
]

# (sku, name, collection, price_paise, sale_price_paise, stock_qty, availability, description)
DEMO_PRODUCTS = [
    (
        "SS-KAJU-KATLI-500",
        "Kaju Katli (500 g)",
        "Mithai",
        64000,
        None,
        None,
        IN_STOCK,
        "Cashew fudge with edible silver varq, made in pure desi ghee.",
    ),
    (
        "SS-MOTICHOOR-LADDU-500",
        "Motichoor Laddu (500 g)",
        "Mithai",
        32000,
        28900,
        40,
        IN_STOCK,
        "Soft boondi laddus with cardamom and melon seeds.",
    ),
    (
        "SS-RASGULLA-1KG",
        "Rasgulla Tin (1 kg)",
        "Mithai",
        38000,
        None,
        25,
        IN_STOCK,
        "Spongy chhena balls in light sugar syrup, 16 pieces.",
    ),
    (
        "SS-GULAB-JAMUN-1KG",
        "Gulab Jamun Tin (1 kg)",
        "Mithai",
        36000,
        None,
        None,
        IN_STOCK,
        "Khoya jamuns soaked in rose and saffron syrup, 16 pieces.",
    ),
    (
        "SS-MILK-CAKE-500",
        "Alwar Milk Cake (500 g)",
        "Mithai",
        42000,
        None,
        12,
        IN_STOCK,
        "Slow-cooked caramelised milk cake with a grainy texture.",
    ),
    (
        "SS-SOAN-PAPDI-250",
        "Soan Papdi (250 g)",
        "Mithai",
        12000,
        9900,
        None,
        IN_STOCK,
        "Flaky gram flour sweet with pistachio slivers.",
    ),
    (
        "SS-ALOO-BHUJIA-400",
        "Aloo Bhujia (400 g)",
        "Namkeen",
        11000,
        None,
        None,
        IN_STOCK,
        "Spicy potato and moth bean sev, Bikaner style.",
    ),
    (
        "SS-KHATTA-MEETHA-400",
        "Khatta Meetha Mix (400 g)",
        "Namkeen",
        10500,
        None,
        None,
        IN_STOCK,
        "Sweet and tangy mix of sev, peanuts, raisins and cornflakes.",
    ),
    (
        "SS-METHI-MATHRI-250",
        "Methi Mathri (250 g)",
        "Namkeen",
        9000,
        None,
        60,
        IN_STOCK,
        "Crisp fenugreek crackers, perfect with masala chai.",
    ),
    (
        "SS-PUNJABI-SAMOSA-6",
        "Punjabi Samosa (6 pcs)",
        "Namkeen",
        14000,
        None,
        None,
        OUT_OF_STOCK,
        "Potato and pea samosas, fried fresh every evening.",
    ),
    (
        "SS-DIWALI-BOX-1KG",
        "Diwali Assorted Box (1 kg)",
        "Gift boxes",
        129900,
        114900,
        15,
        IN_STOCK,
        "Kaju katli, motichoor laddu, milk cake and soan papdi in a festive box.",
    ),
    (
        "SS-DRY-FRUIT-BOX-500",
        "Dry Fruit Gift Box (500 g)",
        "Gift boxes",
        99900,
        None,
        None,
        IN_STOCK,
        "Almonds, cashews, pistachios and raisins in a wooden box.",
    ),
]


def seed(workspace) -> None:
    collections = {}
    for position, (name, description) in enumerate(DEMO_COLLECTIONS):
        collection = Collection.objects.filter(workspace=workspace, name__iexact=name).first()
        if collection is None:
            collection = Collection.objects.create(
                workspace=workspace, name=name, description=description, position=position
            )
        collections[name] = collection

    for position, row in enumerate(DEMO_PRODUCTS):
        sku, name, collection, price, sale_price, stock_qty, availability, description = row
        Product.objects.get_or_create(
            workspace=workspace,
            sku=sku,
            defaults={
                "name": name,
                "collection": collections[collection],
                "price_paise": price,
                "sale_price_paise": sale_price,
                "stock_qty": stock_qty,
                "availability": availability,
                "description": description,
                "position": position,
            },
        )
