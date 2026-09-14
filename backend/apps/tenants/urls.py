from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import AcceptInvitationView, InvitationViewSet, MemberViewSet, WorkspaceViewSet

app_name = "tenants"

router = SimpleRouter()
router.register("members", MemberViewSet, basename="member")
router.register("invitations", InvitationViewSet, basename="invitation")
router.register("", WorkspaceViewSet, basename="workspace")

urlpatterns = [
    path("invitations/accept/", AcceptInvitationView.as_view(), name="invitation-accept"),
    *router.urls,
]
