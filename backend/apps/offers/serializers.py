"""Offers API serializers (docs/contracts/services-and-offers.md, "Offers")."""

import re

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.catalog.models import Product
from apps.inbox.serializers import ConversationContactSerializer, UserSummarySerializer

from . import services
from .models import CODE_PATTERN, OfferClaim, OfferCode

MAX_PERCENT = 90
MIN_AMOUNT_PAISE = 100
MAX_CHOSEN_ITEMS = 100
_CODE_RE = re.compile(CODE_PATTERN)


class OfferItemSerializer(serializers.ModelSerializer):
    """A catalog item an ``items`` offer applies to."""

    class Meta:
        model = Product
        fields = ("id", "name", "kind", "price_paise", "is_active")
        read_only_fields = fields


class OfferCodeSerializer(serializers.ModelSerializer):
    products = OfferItemSerializer(many=True, read_only=True)
    product_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        max_length=MAX_CHOSEN_ITEMS,
        help_text='The catalog items an "items" offer applies to; ignored for other values.',
    )
    claims_count = serializers.SerializerMethodField()
    redeemed_count = serializers.SerializerMethodField()

    class Meta:
        model = OfferCode
        fields = (
            "id",
            "code",
            "title",
            "reply_text",
            "discount_type",
            "discount_value",
            "max_discount_paise",
            "min_order_paise",
            "applies_to",
            "products",
            "product_ids",
            "starts_at",
            "ends_at",
            "max_uses",
            "max_uses_per_contact",
            "is_active",
            "claims_count",
            "redeemed_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
        extra_kwargs = {
            "code": {"validators": []},
            "max_uses": {"min_value": 1},
            "max_uses_per_contact": {"min_value": 1},
            "reply_text": {"allow_blank": False},
        }

    @extend_schema_field(OpenApiTypes.INT)
    def get_claims_count(self, offer) -> int:
        value = getattr(offer, "claims_count", None)
        return value if value is not None else offer.claims.count()

    @extend_schema_field(OpenApiTypes.INT)
    def get_redeemed_count(self, offer) -> int:
        value = getattr(offer, "redeemed_count", None)
        if value is not None:
            return value
        return offer.claims.filter(status=OfferClaim.Status.REDEEMED).count()

    def validate_code(self, value: str) -> str:
        code = (value or "").strip()
        if not _CODE_RE.fullmatch(code):
            raise serializers.ValidationError("Use 2-20 letters, digits, '-' or '_'.")
        code = code.upper()
        workspace = self.context["workspace"]
        clashes = OfferCode.objects.filter(workspace=workspace, code=code)
        if self.instance is not None:
            clashes = clashes.exclude(pk=self.instance.pk)
        if clashes.exists():
            raise serializers.ValidationError("An offer with this code already exists.")
        collision = services.code_collision(workspace, code)
        if collision:
            raise serializers.ValidationError(collision)
        return code

    def validate(self, attrs):
        def current(name):
            if name in attrs:
                return attrs[name]
            return getattr(self.instance, name) if self.instance is not None else None

        discount_type = current("discount_type") or OfferCode.DiscountType.NONE
        value = current("discount_value") or 0
        errors = {}
        if discount_type == OfferCode.DiscountType.NONE:
            attrs["discount_value"] = 0
            attrs["max_discount_paise"] = None
        elif discount_type == OfferCode.DiscountType.PERCENT:
            if not 1 <= value <= MAX_PERCENT:
                errors["discount_value"] = [f"Use a percentage from 1 to {MAX_PERCENT}."]
        elif discount_type == OfferCode.DiscountType.AMOUNT:
            if value < MIN_AMOUNT_PAISE:
                errors["discount_value"] = ["Use an amount of at least ₹1 (100 paise)."]
            if current("max_discount_paise") is not None:
                errors["max_discount_paise"] = ["A cap applies only to percentage discounts."]
        applies_to = current("applies_to") or OfferCode.AppliesTo.ALL
        if applies_to == OfferCode.AppliesTo.ITEMS:
            if "product_ids" in attrs:
                ids = list(dict.fromkeys(attrs["product_ids"]))
                chosen = list(
                    Product.objects.filter(workspace=self.context["workspace"], pk__in=ids)
                )
                if len(chosen) != len(ids):
                    errors["product_ids"] = ["Some of these items are not in your catalog."]
                attrs["product_ids"] = chosen
            else:
                chosen = [] if self.instance is None else list(self.instance.products.all())
            if "product_ids" not in errors and not chosen:
                errors["product_ids"] = ["Choose at least one product or service."]
        else:
            attrs["product_ids"] = []
        starts_at, ends_at = current("starts_at"), current("ends_at")
        if starts_at and ends_at and ends_at <= starts_at:
            errors["ends_at"] = ["The end must be after the start."]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        chosen = validated_data.pop("product_ids", [])
        offer = super().create(validated_data)
        offer.products.set(chosen)
        return offer

    def update(self, instance, validated_data):
        chosen = validated_data.pop("product_ids", None)
        offer = super().update(instance, validated_data)
        if chosen is not None:
            offer.products.set(chosen)
        return offer


class OfferClaimSerializer(serializers.ModelSerializer):
    offer = serializers.UUIDField(source="offer_id", read_only=True)
    offer_code = serializers.CharField(source="offer.code", read_only=True)
    contact = ConversationContactSerializer(read_only=True)
    conversation_id = serializers.UUIDField(read_only=True, allow_null=True)
    order_id = serializers.UUIDField(read_only=True, allow_null=True)
    order_number = serializers.SerializerMethodField()
    from_ad = serializers.BooleanField(read_only=True)
    redeemed_by = UserSummarySerializer(read_only=True, allow_null=True)

    class Meta:
        model = OfferClaim
        fields = (
            "id",
            "offer",
            "offer_code",
            "status",
            "contact",
            "conversation_id",
            "order_id",
            "order_number",
            "discount_paise",
            "bill_paise",
            "from_ad",
            "ad_source_id",
            "ad_source_url",
            "ad_headline",
            "ctwa_clid",
            "redeemed_at",
            "redeemed_by",
            "created_at",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_order_number(self, claim) -> str | None:
        return claim.order.number if claim.order_id and claim.order else None


class RedeemClaimSerializer(serializers.Serializer):
    bill_paise = serializers.IntegerField(min_value=0, required=False, allow_null=True)


class CounterRedeemSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=40)
    phone = serializers.CharField(max_length=32)
    bill_paise = serializers.IntegerField(min_value=0, required=False, allow_null=True)


class OfferStatsDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    claims = serializers.IntegerField()
    redeemed = serializers.IntegerField()


class OfferStatsSerializer(serializers.Serializer):
    claims = serializers.IntegerField()
    from_ads = serializers.IntegerField()
    applied = serializers.IntegerField()
    redeemed = serializers.IntegerField()
    discount_paise = serializers.IntegerField()
    revenue_paise = serializers.IntegerField()
    daily = OfferStatsDaySerializer(many=True)
