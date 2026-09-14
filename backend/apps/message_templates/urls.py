from rest_framework.routers import SimpleRouter

from .views import MessageTemplateViewSet

app_name = "message_templates"

router = SimpleRouter()
router.register("", MessageTemplateViewSet, basename="template")

urlpatterns = router.urls
