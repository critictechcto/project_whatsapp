"""Response shapes for docs/contracts/analytics.md. ``FooSerializer`` produces component ``Foo``."""

from rest_framework import serializers

from apps.campaigns.models import Campaign
from apps.orders.models import Order

from .schema_enums import MESSAGE_SOURCES, PAYMENT_METHODS


def rate_field():
    return serializers.DecimalField(
        max_digits=5, decimal_places=4, allow_null=True, help_text="0-1, or null"
    )


class AnalyticsRangeSerializer(serializers.Serializer):
    to = serializers.DateField()
    time_zone = serializers.CharField()
    previous_from = serializers.DateField()
    previous_to = serializers.DateField()

    def get_fields(self):
        fields = super().get_fields()
        return {"from": serializers.DateField(), **fields}


class AnalyticsTotalsSerializer(serializers.Serializer):
    messages_sent = serializers.IntegerField()
    messages_delivered = serializers.IntegerField()
    messages_read = serializers.IntegerField()
    messages_failed = serializers.IntegerField()
    messages_received = serializers.IntegerField()
    delivery_rate = rate_field()
    read_rate = rate_field()
    conversations_started = serializers.IntegerField()
    contacts_added = serializers.IntegerField()
    contacts_opted_in = serializers.IntegerField()
    contacts_opted_out = serializers.IntegerField()
    campaigns_sent = serializers.IntegerField()
    automation_runs = serializers.IntegerField()
    orders = serializers.IntegerField(allow_null=True)
    revenue_paise = serializers.IntegerField(allow_null=True)


class AnalyticsOverviewSerializer(serializers.Serializer):
    range = AnalyticsRangeSerializer()
    current = AnalyticsTotalsSerializer()
    previous = AnalyticsTotalsSerializer()


class AnalyticsMessagePointSerializer(serializers.Serializer):
    date = serializers.DateField()
    sent = serializers.IntegerField()
    delivered = serializers.IntegerField()
    read = serializers.IntegerField()
    failed = serializers.IntegerField()
    received = serializers.IntegerField()


class AnalyticsSourceRowSerializer(serializers.Serializer):
    source = serializers.ChoiceField(choices=MESSAGE_SOURCES)
    sent = serializers.IntegerField()
    delivered = serializers.IntegerField()
    read = serializers.IntegerField()
    failed = serializers.IntegerField()
    delivery_rate = rate_field()
    read_rate = rate_field()


class AnalyticsCategoryRowSerializer(serializers.Serializer):
    category = serializers.CharField(allow_blank=True)
    sent = serializers.IntegerField()
    delivered = serializers.IntegerField()
    read = serializers.IntegerField()
    failed = serializers.IntegerField()


class AnalyticsFailureRowSerializer(serializers.Serializer):
    error_code = serializers.CharField(allow_blank=True)
    count = serializers.IntegerField()


class AnalyticsMessagesSerializer(serializers.Serializer):
    range = AnalyticsRangeSerializer()
    series = AnalyticsMessagePointSerializer(many=True)
    by_source = AnalyticsSourceRowSerializer(many=True)
    by_category = AnalyticsCategoryRowSerializer(many=True)
    failure_reasons = AnalyticsFailureRowSerializer(many=True)


class AnalyticsTemplateRowSerializer(serializers.Serializer):
    template_id = serializers.UUIDField(allow_null=True)
    name = serializers.CharField(allow_blank=True)
    language = serializers.CharField(allow_blank=True)
    category = serializers.CharField(allow_blank=True)
    sent = serializers.IntegerField()
    delivered = serializers.IntegerField()
    read = serializers.IntegerField()
    failed = serializers.IntegerField()
    delivery_rate = rate_field()
    read_rate = rate_field()


class AnalyticsTemplatesSerializer(serializers.Serializer):
    range = AnalyticsRangeSerializer()
    results = AnalyticsTemplateRowSerializer(many=True)


class AnalyticsCampaignRowSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    status = serializers.ChoiceField(choices=Campaign.Status.values)
    started_at = serializers.DateTimeField()
    total_count = serializers.IntegerField()
    sent_count = serializers.IntegerField()
    delivered_count = serializers.IntegerField()
    read_count = serializers.IntegerField()
    failed_count = serializers.IntegerField()
    replied_count = serializers.IntegerField()
    delivery_rate = rate_field()
    read_rate = rate_field()
    reply_rate = rate_field()


class AnalyticsCampaignsSerializer(serializers.Serializer):
    range = AnalyticsRangeSerializer()
    results = AnalyticsCampaignRowSerializer(many=True)


class AnalyticsTeamRowSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    name = serializers.CharField()
    email = serializers.CharField()
    role = serializers.CharField()
    messages_sent = serializers.IntegerField()
    conversations_assigned = serializers.IntegerField()
    conversations_closed = serializers.IntegerField()


class AnalyticsTeamSerializer(serializers.Serializer):
    range = AnalyticsRangeSerializer()
    results = AnalyticsTeamRowSerializer(many=True)


class AnalyticsCommercePointSerializer(serializers.Serializer):
    date = serializers.DateField()
    orders = serializers.IntegerField()
    revenue_paise = serializers.IntegerField()


class AnalyticsOrderStatusRowSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.values)
    count = serializers.IntegerField()


class AnalyticsPaymentMethodRowSerializer(serializers.Serializer):
    payment_method = serializers.ChoiceField(choices=PAYMENT_METHODS, allow_blank=True)
    orders = serializers.IntegerField()
    revenue_paise = serializers.IntegerField()


class AnalyticsProductRowSerializer(serializers.Serializer):
    product_id = serializers.UUIDField(allow_null=True)
    name = serializers.CharField()
    quantity = serializers.IntegerField()
    revenue_paise = serializers.IntegerField()


class AnalyticsCommerceSerializer(serializers.Serializer):
    range = AnalyticsRangeSerializer()
    series = AnalyticsCommercePointSerializer(many=True)
    orders = serializers.IntegerField()
    paid_orders = serializers.IntegerField()
    revenue_paise = serializers.IntegerField()
    average_order_paise = serializers.IntegerField(allow_null=True)
    by_status = AnalyticsOrderStatusRowSerializer(many=True)
    by_payment_method = AnalyticsPaymentMethodRowSerializer(many=True)
    top_products = AnalyticsProductRowSerializer(many=True)
