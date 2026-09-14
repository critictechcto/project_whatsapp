import pytest
from django.conf import settings

from common.tests.fakes import install_module
from config import routing
from config.routing import collect_websocket_urlpatterns

INBOX_ROUTE = object()
INBOX_TYPING_ROUTE = object()
CAMPAIGN_ROUTE = object()


def test_collects_patterns_in_installed_apps_order(monkeypatch):
    install_module(monkeypatch, "apps.fakeinbox", package=True)
    install_module(
        monkeypatch,
        "apps.fakeinbox.routing",
        websocket_urlpatterns=[INBOX_ROUTE, INBOX_TYPING_ROUTE],
    )
    install_module(monkeypatch, "apps.fakecampaigns", package=True)
    install_module(
        monkeypatch, "apps.fakecampaigns.routing", websocket_urlpatterns=[CAMPAIGN_ROUTE]
    )
    install_module(monkeypatch, "apps.norouting", package=True)
    install_module(monkeypatch, "apps.emptyrouting", package=True)
    install_module(monkeypatch, "apps.emptyrouting.routing")  # no websocket_urlpatterns

    patterns = collect_websocket_urlpatterns(
        ["apps.fakeinbox", "apps.norouting", "apps.emptyrouting", "apps.fakecampaigns"]
    )

    assert patterns == [INBOX_ROUTE, INBOX_TYPING_ROUTE, CAMPAIGN_ROUTE]


def test_ignores_apps_outside_the_apps_package(monkeypatch):
    install_module(monkeypatch, "thirdparty", package=True)
    install_module(monkeypatch, "thirdparty.routing", websocket_urlpatterns=[INBOX_ROUTE])

    assert collect_websocket_urlpatterns(["thirdparty", "channels", "common"]) == []


@pytest.mark.parametrize("apps", [[], ()])
def test_no_apps(apps):
    assert collect_websocket_urlpatterns(apps) == []


def test_module_patterns_match_installed_apps():
    assert isinstance(routing.websocket_urlpatterns, list)
    assert routing.websocket_urlpatterns == collect_websocket_urlpatterns(settings.INSTALLED_APPS)
