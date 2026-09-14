"""Catalog API (docs/contracts/wave-3-commerce.md, "Catalog").

Reads are open to every member; writes need the admin role and the plan's ``commerce`` feature
(409 ``commerce_not_enabled``). Disconnecting a Meta catalog is always allowed.
"""

import uuid

from django.db.models import Count, Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response

from apps.billing import entitlements
from common.pagination import DefaultCursorPagination
from common.roles import Role
from common.tenancy import WorkspaceScopedGenericViewSet

from . import imports, meta, writes
from .exceptions import CommerceNotEnabled
from .models import Collection, MetaCatalog, Product
from .schema_enums import META_REVIEW_STATUSES, PRODUCT_AVAILABILITIES
from .serializers import (
    AvailableCatalogSerializer,
    CollectionSerializer,
    CollectionWriteSerializer,
    CommerceSettingsSerializer,
    MetaCatalogConnectSerializer,
    MetaCatalogSerializer,
    ProductImageUploadSerializer,
    ProductImportResultSerializer,
    ProductImportUploadSerializer,
    ProductSerializer,
    ProductWriteSerializer,
    ReorderSerializer,
)

TRUE_VALUES = frozenset({"true", "1", "yes"})
FALSE_VALUES = frozenset({"false", "0", "no"})


class PositionCursorPagination(DefaultCursorPagination):
    ordering = ("position", "name", "id")


class CatalogViewSet(WorkspaceScopedGenericViewSet):
    filter_backends: list = []
    lookup_value_converter = "uuid"
    read_role = Role.VIEWER
    write_role = Role.ADMIN
    # Unsafe actions that don't need the plan's commerce feature.
    commerce_exempt_actions: frozenset[str] = frozenset()

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if (
            request.method not in SAFE_METHODS
            and self.action not in self.commerce_exempt_actions
            and not entitlements.has_feature(self.workspace, entitlements.COMMERCE)
        ):
            raise CommerceNotEnabled()

    def query_choice(self, name: str, choices) -> str | None:
        value = self.request.query_params.get(name)
        if value in (None, ""):
            return None
        if value not in choices:
            raise serializers.ValidationError({name: [f"Use one of: {', '.join(choices)}."]})
        return value

    def query_uuid(self, name: str) -> uuid.UUID | None:
        value = self.request.query_params.get(name)
        if value in (None, ""):
            return None
        try:
            return uuid.UUID(value)
        except ValueError:
            raise serializers.ValidationError({name: ["Must be a valid UUID."]}) from None

    def query_bool(self, name: str) -> bool | None:
        value = self.request.query_params.get(name)
        if value in (None, ""):
            return None
        if value.lower() in TRUE_VALUES:
            return True
        if value.lower() in FALSE_VALUES:
            return False
        raise serializers.ValidationError({name: ["Use true or false."]})

    def paginated(self, queryset, serializer_class):
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(serializer_class(page, many=True).data)

    def validated(self, serializer_class, **kwargs) -> dict:
        serializer = serializer_class(
            data=self.request.data, context=self.get_serializer_context(), **kwargs
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class ProductViewSet(CatalogViewSet):
    queryset = Product.objects.select_related("collection")
    serializer_class = ProductSerializer
    pagination_class = PositionCursorPagination

    def product_response(self, product, status_code=status.HTTP_200_OK) -> Response:
        product = self.get_queryset().get(pk=product.pk)
        return Response(ProductSerializer(product).data, status=status_code)

    @extend_schema(
        operation_id="catalog_products_list",
        parameters=[
            OpenApiParameter("collection", OpenApiTypes.STR, description="Collection id, or none."),
            OpenApiParameter("is_active", OpenApiTypes.BOOL),
            OpenApiParameter("availability", OpenApiTypes.STR, enum=PRODUCT_AVAILABILITIES),
            OpenApiParameter("meta_review_status", OpenApiTypes.STR, enum=META_REVIEW_STATUSES),
            OpenApiParameter("search", OpenApiTypes.STR, description="Name or SKU."),
        ],
        responses=ProductSerializer(many=True),
    )
    def list(self, request):
        queryset = self.get_queryset()
        collection = request.query_params.get("collection")
        if collection == "none":
            queryset = queryset.filter(collection__isnull=True)
        elif collection_id := self.query_uuid("collection"):
            queryset = queryset.filter(collection_id=collection_id)
        if (is_active := self.query_bool("is_active")) is not None:
            queryset = queryset.filter(is_active=is_active)
        if availability := self.query_choice("availability", PRODUCT_AVAILABILITIES):
            queryset = queryset.filter(availability=availability)
        if review := self.query_choice("meta_review_status", META_REVIEW_STATUSES):
            queryset = queryset.filter(meta_review_status=review)
        if search := request.query_params.get("search", "").strip():
            queryset = queryset.filter(Q(name__icontains=search) | Q(sku__icontains=search))
        return self.paginated(queryset, ProductSerializer)

    @extend_schema(
        operation_id="catalog_products_create",
        request=ProductWriteSerializer,
        responses={201: ProductSerializer},
        description="409-free: a duplicate SKU is a 400 invalid error on sku.",
    )
    def create(self, request):
        product = writes.create_product(self.workspace, self.validated(ProductWriteSerializer))
        return self.product_response(product, status.HTTP_201_CREATED)

    @extend_schema(operation_id="catalog_products_retrieve", responses=ProductSerializer)
    def retrieve(self, request, pk=None):
        return Response(ProductSerializer(self.get_object()).data)

    @extend_schema(
        operation_id="catalog_products_partial_update",
        request=ProductWriteSerializer,
        responses=ProductSerializer,
        description="sku is read-only after create.",
    )
    def partial_update(self, request, pk=None):
        product = self.get_object()
        writes.update_product(product, self.validated(ProductWriteSerializer, partial=True))
        return self.product_response(product)

    @extend_schema(
        operation_id="catalog_products_destroy",
        responses={204: None},
        description="Queues a Meta catalog delete; past order items keep their snapshots.",
    )
    def destroy(self, request, pk=None):
        writes.delete_product(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        methods=["POST"],
        operation_id="catalog_products_image_create",
        request={"multipart/form-data": ProductImageUploadSerializer},
        responses=ProductSerializer,
    )
    @extend_schema(
        methods=["DELETE"],
        operation_id="catalog_products_image_destroy",
        request=None,
        responses=ProductSerializer,
    )
    @action(
        detail=True,
        methods=["post", "delete"],
        parser_classes=[MultiPartParser, FormParser],
    )
    def image(self, request, pk=None):
        product = self.get_object()
        if request.method == "DELETE":
            writes.remove_product_image(product)
        else:
            upload = self.validated(ProductImageUploadSerializer)["file"]
            writes.set_product_image(product, upload)
        return self.product_response(product)

    @extend_schema(
        operation_id="catalog_products_import_create",
        request={"multipart/form-data": ProductImportUploadSerializer},
        responses=ProductImportResultSerializer,
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="import",
        parser_classes=[MultiPartParser, FormParser],
    )
    def import_products(self, request):
        upload = self.validated(ProductImportUploadSerializer)["file"]
        try:
            result = imports.import_products(self.workspace, upload)
        except imports.ImportRejected as exc:
            raise serializers.ValidationError({"file": [str(exc)]}) from None
        return Response(ProductImportResultSerializer(result).data)

    @extend_schema(
        operation_id="catalog_products_reorder_create",
        request=ReorderSerializer,
        responses={204: None},
    )
    @action(detail=False, methods=["post"])
    def reorder(self, request):
        writes.reorder(Product, self.workspace, self.validated(ReorderSerializer)["ids"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class CollectionViewSet(CatalogViewSet):
    queryset = Collection.objects.all()
    serializer_class = CollectionSerializer
    pagination_class = PositionCursorPagination

    def get_queryset(self):
        return super().get_queryset().annotate(product_count=Count("products"))

    def collection_response(self, collection, status_code=status.HTTP_200_OK) -> Response:
        collection = self.get_queryset().get(pk=collection.pk)
        return Response(CollectionSerializer(collection).data, status=status_code)

    @extend_schema(
        operation_id="catalog_collections_list", responses=CollectionSerializer(many=True)
    )
    def list(self, request):
        return self.paginated(self.get_queryset(), CollectionSerializer)

    @extend_schema(
        operation_id="catalog_collections_create",
        request=CollectionWriteSerializer,
        responses={201: CollectionSerializer},
    )
    def create(self, request):
        data = self.validated(CollectionWriteSerializer)
        collection = writes.create_collection(self.workspace, data)
        return self.collection_response(collection, status.HTTP_201_CREATED)

    @extend_schema(operation_id="catalog_collections_retrieve", responses=CollectionSerializer)
    def retrieve(self, request, pk=None):
        return Response(CollectionSerializer(self.get_object()).data)

    @extend_schema(
        operation_id="catalog_collections_partial_update",
        request=CollectionWriteSerializer,
        responses=CollectionSerializer,
    )
    def partial_update(self, request, pk=None):
        collection = self.get_object()
        writes.update_collection(
            collection, self.validated(CollectionWriteSerializer, partial=True)
        )
        return self.collection_response(collection)

    @extend_schema(
        operation_id="catalog_collections_destroy",
        responses={204: None},
        description="Its products move out of the collection.",
    )
    def destroy(self, request, pk=None):
        self.get_object().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="catalog_collections_reorder_create",
        request=ReorderSerializer,
        responses={204: None},
    )
    @action(detail=False, methods=["post"])
    def reorder(self, request):
        writes.reorder(Collection, self.workspace, self.validated(ReorderSerializer)["ids"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MetaCatalogViewSet(CatalogViewSet):
    queryset = MetaCatalog.objects.select_related("waba")
    serializer_class = MetaCatalogSerializer
    action_roles = {"available": Role.ADMIN}
    commerce_exempt_actions = frozenset({"destroy"})

    def catalog_response(self, meta_catalog, status_code=status.HTTP_200_OK) -> Response:
        meta_catalog = self.get_queryset().get(pk=meta_catalog.pk)
        return Response(MetaCatalogSerializer(meta_catalog).data, status=status_code)

    @extend_schema(
        operation_id="catalog_meta_catalogs_list", responses=MetaCatalogSerializer(many=True)
    )
    def list(self, request):
        return self.paginated(self.get_queryset(), MetaCatalogSerializer)

    @extend_schema(
        operation_id="catalog_meta_catalogs_create",
        request=MetaCatalogConnectSerializer,
        responses={201: MetaCatalogSerializer, 200: MetaCatalogSerializer},
        description=(
            "Connects (201) or replaces the WABA's connected catalog (200). "
            "409 catalog_permissions_missing when the token lacks catalog permissions."
        ),
    )
    def create(self, request):
        data = self.validated(MetaCatalogConnectSerializer)
        waba = meta.workspace_waba(self.workspace, data["waba_id"])
        meta_catalog, created = meta.connect_catalog(
            self.workspace,
            waba=waba,
            user=request.user,
            catalog_id=data.get("catalog_id"),
            create_name=data.get("create_name"),
        )
        return self.catalog_response(
            meta_catalog, status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )

    @extend_schema(
        operation_id="catalog_meta_catalogs_available_list",
        parameters=[OpenApiParameter("waba_id", OpenApiTypes.UUID, required=True)],
        responses=AvailableCatalogSerializer(many=True),
        description="Catalogs owned by the seller's Meta business (unpaginated).",
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def available(self, request):
        waba_pk = self.query_uuid("waba_id")
        if waba_pk is None:
            raise serializers.ValidationError({"waba_id": ["This parameter is required."]})
        waba = meta.workspace_waba(self.workspace, waba_pk)
        return Response(AvailableCatalogSerializer(meta.available_catalogs(waba), many=True).data)

    @extend_schema(operation_id="catalog_meta_catalogs_retrieve", responses=MetaCatalogSerializer)
    def retrieve(self, request, pk=None):
        return Response(MetaCatalogSerializer(self.get_object()).data)

    @extend_schema(
        operation_id="catalog_meta_catalogs_destroy",
        responses={204: None},
        description="Disconnects locally; the store falls back to bot mode.",
    )
    def destroy(self, request, pk=None):
        meta.disconnect_catalog(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="catalog_meta_catalogs_sync_create",
        request=None,
        responses={202: MetaCatalogSerializer},
        description="Queue a full resync.",
    )
    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        meta_catalog = meta.resync(self.get_object())
        return self.catalog_response(meta_catalog, status.HTTP_202_ACCEPTED)

    @extend_schema(
        operation_id="catalog_meta_catalogs_commerce_settings_partial_update",
        request=CommerceSettingsSerializer,
        responses=MetaCatalogSerializer,
    )
    @action(detail=True, methods=["patch"], url_path="commerce-settings")
    def commerce_settings(self, request, pk=None):
        meta_catalog = self.get_object()
        data = self.validated(CommerceSettingsSerializer)
        meta.update_commerce_settings(
            meta_catalog,
            phone_number_id=data["phone_number_id"],
            is_cart_enabled=data.get("is_cart_enabled"),
            is_catalog_visible=data.get("is_catalog_visible"),
        )
        return self.catalog_response(meta_catalog)
