from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("overview/", views.OverviewView.as_view(), name="overview"),
    path("messages/", views.MessagesView.as_view(), name="messages"),
    path("templates/", views.TemplatesView.as_view(), name="templates"),
    path("campaigns/", views.CampaignsView.as_view(), name="campaigns"),
    path("team/", views.TeamView.as_view(), name="team"),
    path("commerce/", views.CommerceView.as_view(), name="commerce"),
    path("export/", views.ExportView.as_view(), name="export"),
]
