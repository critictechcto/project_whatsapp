"""Catalog API (docs/contracts/wave-3-commerce.md, "Catalog").

Reads are implemented against the models. Writes, uploads, imports and Meta catalog actions
are contract stubs that answer 501 ``not_implemented`` after the role and object checks.
"""

import uuid

from django.db.models import Count, Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from common.pagination import DefaultCursorPagination
from common.roles import Role
from common.tenancy import WorkspaceScopedGenericViewSet

from .exceptions import EndpointNotImplemented
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


class ProductViewSet(CatalogViewSet):
    queryset = Product.objects.select_related("collection")
    serializer_class = ProductSerializer
    pagination_class = PositionCursorPagination

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
        raise EndpointNotImplemented()

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
        self.get_object()
        raise EndpointNotImplemented()

    @extend_schema(
        operation_id="catalog_products_destroy",
        responses={204: None},
        description="Queues a Meta catalog delete; past order items keep their snapshots.",
    )
    def destroy(self, request, pk=None):
        self.get_object()
        raise EndpointNotImplemented()

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
        self.get_object()
        raise EndpointNotImplemented()

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
        raise EndpointNotImplemented()

    @extend_schema(
        operation_id="catalog_products_reorder_create",
        request=ReorderSerializer,
        responses={204: None},
    )
    @action(detail=False, methods=["post"])
    def reorder(self, request):
        raise EndpointNotImplemented()


class CollectionViewSet(CatalogViewSet):
    queryset = Collection.objects.all()
    serializer_class = CollectionSerializer
    pagination_class = PositionCursorPagination

    def get_queryset(self):
        return super().get_queryset().annotate(product_count=Count("products"))

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
        raise EndpointNotImplemented()

    @extend_schema(operation_id="catalog_collections_retrieve", responses=CollectionSerializer)
    def retrieve(self, request, pk=None):
        return Response(CollectionSerializer(self.get_object()).data)

    @extend_schema(
        operation_id="catalog_collections_partial_update",
        request=CollectionWriteSerializer,
        responses=CollectionSerializer,
    )
    def partial_update(self, request, pk=None):
        self.get_object()
        raise EndpointNotImplemented()

    @extend_schema(
        operation_id="catalog_collections_destroy",
        responses={204: None},
        description="Its products move out of the collection.",
    )
    def destroy(self, request, pk=None):
        self.get_object()
        raise EndpointNotImplemented()

    @extend_schema(
        operation_id="catalog_collections_reorder_create",
        request=ReorderSerializer,
        responses={204: None},
    )
    @action(detail=False, methods=["post"])
    def reorder(self, request):
        raise EndpointNotImplemented()


class MetaCatalogViewSet(CatalogViewSet):
    queryset = MetaCatalog.objects.select_related("waba")
    serializer_class = MetaCatalogSerializer
    action_roles = {"available": Role.ADMIN}

    @extend_schema(
        operation_id="catalog_meta_catalogs_list", responses=MetaCatalogSerializer(many=True)
    )
    def list(self, request):
        return self.paginated(self.get_queryset(), MetaCatalogSerializer)

    @extend_schema(
        operation_id="catalog_meta_catalogs_create",
        request=MetaCatalogConnectSerializer,
        responses={201: MetaCatalogSerializer},
        description="409 catalog_permissions_missing when the token lacks catalog permissions.",
    )
    def create(self, request):
        raise EndpointNotImplemented()

    @extend_schema(
        operation_id="catalog_meta_catalogs_available_list",
        parameters=[OpenApiParameter("waba_id", OpenApiTypes.UUID, required=True)],
        responses=AvailableCatalogSerializer(many=True),
        description="Catalogs owned by the seller's Meta business (unpaginated).",
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def available(self, request):
        raise EndpointNotImplemented()

    @extend_schema(operation_id="catalog_meta_catalogs_retrieve", responses=MetaCatalogSerializer)
    def retrieve(self, request, pk=None):
        return Response(MetaCatalogSerializer(self.get_object()).data)

    @extend_schema(
        operation_id="catalog_meta_catalogs_destroy",
        responses={204: None},
        description="Disconnects locally; the store falls back to bot mode.",
    )
    def destroy(self, request, pk=None):
        self.get_object()
        raise EndpointNotImplemented()

    @extend_schema(
        operation_id="catalog_meta_catalogs_sync_create",
        request=None,
        responses={202: MetaCatalogSerializer},
        description="Queue a full resync.",
    )
    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        self.get_object()
        raise EndpointNotImplemented()

    @extend_schema(
        operation_id="catalog_meta_catalogs_commerce_settings_partial_update",
        request=CommerceSettingsSerializer,
        responses=MetaCatalogSerializer,
    )
    @action(detail=True, methods=["patch"], url_path="commerce-settings")
    def commerce_settings(self, request, pk=None):
        self.get_object()
        raise EndpointNotImplemented()
