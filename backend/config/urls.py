"""Root URL map. Every app is mounted here once; apps own only their own urls.py."""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from common.views import healthz, readyz

api_v1 = [
    path("auth/", include("apps.accounts.urls")),
    path("workspaces/", include("apps.tenants.urls")),
    path("whatsapp/", include("apps.whatsapp.urls")),
    path("templates/", include("apps.message_templates.urls")),
    path("contacts/", include("apps.contacts.urls")),
    path("campaigns/", include("apps.campaigns.urls")),
    path("inbox/", include("apps.inbox.urls")),
    path("automations/", include("apps.automations.urls")),
    path("billing/", include("apps.billing.urls")),
    path("catalog/", include("apps.catalog.urls")),
    path("orders/", include("apps.orders.urls")),
    path("store/", include("apps.orders.store_urls")),
    path("payments/", include("apps.payments.urls")),
    path("seller-alerts/", include("apps.seller_alerts.urls")),
    path("analytics/", include("apps.analytics.urls")),
    path("developer/", include("apps.developer_api.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1)),
    path("webhooks/meta/", include("apps.webhooks.urls")),
    path("webhooks/razorpay/merchants/", include("apps.payments.webhook_urls")),
    path("webhooks/razorpay/", include("apps.billing.webhook_urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
    path("healthz/", healthz, name="healthz"),
    path("readyz/", readyz, name="readyz"),
]
