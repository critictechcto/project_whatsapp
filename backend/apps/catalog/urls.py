from rest_framework.routers import SimpleRouter

from .views import CollectionViewSet, MetaCatalogViewSet, ProductViewSet

app_name = "catalog"

router = SimpleRouter(use_regex_path=False)
router.register("products", ProductViewSet, basename="product")
router.register("collections", CollectionViewSet, basename="collection")
router.register("meta-catalogs", MetaCatalogViewSet, basename="meta-catalog")

urlpatterns = [*router.urls]
