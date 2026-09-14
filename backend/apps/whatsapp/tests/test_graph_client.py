import hashlib
import hmac
import json

import httpx
import pytest
import respx

from apps.whatsapp.client import errors
from apps.whatsapp.client.graph import HttpGraphClient

BASE = "https://graph.facebook.com/v24.0"
TOKEN = "EAAG-customer-secret-token"
PROOF = hmac.new(b"test-app-secret", TOKEN.encode(), hashlib.sha256).hexdigest()


@pytest.fixture
def graph():
    with respx.mock(assert_all_called=True) as router:
        yield router


@pytest.fixture
def client():
    return HttpGraphClient(access_token=TOKEN, http_client=httpx.Client())


@pytest.fixture
def app_client():
    return HttpGraphClient(http_client=httpx.Client())


def ok(body=None):
    return httpx.Response(200, json=body if body is not None else {"success": True})


def assert_customer_auth(request):
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert request.url.params["appsecret_proof"] == PROOF


def body_of(request):
    return json.loads(request.content)


# --- App-level calls ---------------------------------------------------------------------------


def test_exchange_code_uses_app_credentials(graph, app_client):
    route = graph.get(f"{BASE}/oauth/access_token").mock(
        return_value=ok({"access_token": TOKEN, "token_type": "bearer"})
    )

    assert app_client.exchange_code("the-code") == {"access_token": TOKEN, "token_type": "bearer"}

    request = route.calls.last.request
    assert dict(request.url.params) == {
        "client_id": "1234567890",
        "client_secret": "test-app-secret",
        "code": "the-code",
    }
    assert "Authorization" not in request.headers


def test_debug_token_unwraps_data(graph, app_client):
    data = {"app_id": "1234567890", "is_valid": True, "granular_scopes": []}
    route = graph.get(f"{BASE}/debug_token").mock(return_value=ok({"data": data}))

    assert app_client.debug_token(TOKEN) == data

    params = route.calls.last.request.url.params
    assert params["input_token"] == TOKEN
    assert params["access_token"] == "1234567890|test-app-secret"


# --- Business account --------------------------------------------------------------------------


def test_get_waba(graph, client):
    route = graph.get(f"{BASE}/111").mock(return_value=ok({"id": "111", "name": "Shop"}))

    assert client.get_waba("111") == {"id": "111", "name": "Shop"}

    request = route.calls.last.request
    assert_customer_auth(request)
    assert "message_template_namespace" in request.url.params["fields"]


def test_list_phone_numbers_follows_paging(graph, client):
    next_url = f"{BASE}/111/phone_numbers?after=CURSOR&limit=1"

    def respond(request):
        if request.url.params.get("after") == "CURSOR":
            return ok({"data": [{"id": "p2"}], "paging": {"cursors": {"after": "END"}}})
        return ok({"data": [{"id": "p1"}], "paging": {"next": next_url}})

    route = graph.get(f"{BASE}/111/phone_numbers").mock(side_effect=respond)

    assert [n["id"] for n in client.list_phone_numbers("111")] == ["p1", "p2"]
    assert route.call_count == 2
    for call in route.calls:
        assert_customer_auth(call.request)
    assert "messaging_limit_tier" in route.calls[0].request.url.params["fields"]


def test_list_phone_numbers_refuses_foreign_paging_host(graph, client):
    graph.get(f"{BASE}/111/phone_numbers").mock(
        return_value=ok({"data": [], "paging": {"next": "https://evil.example/steal"}})
    )

    with pytest.raises(errors.InvalidParameterError):
        client.list_phone_numbers("111")


def test_get_phone_number(graph, client):
    route = graph.get(f"{BASE}/222").mock(return_value=ok({"id": "222"}))

    assert client.get_phone_number("222") == {"id": "222"}
    assert_customer_auth(route.calls.last.request)
    assert "quality_rating" in route.calls.last.request.url.params["fields"]


def test_subscribe_and_unsubscribe_app(graph, client):
    subscribe = graph.post(f"{BASE}/111/subscribed_apps").mock(return_value=ok())
    unsubscribe = graph.delete(f"{BASE}/111/subscribed_apps").mock(return_value=ok())

    assert client.subscribe_app("111") == {"success": True}
    assert client.unsubscribe_app("111") == {"success": True}
    assert_customer_auth(subscribe.calls.last.request)
    assert_customer_auth(unsubscribe.calls.last.request)


def test_register_and_deregister_phone(graph, client):
    register = graph.post(f"{BASE}/222/register").mock(return_value=ok())
    deregister = graph.post(f"{BASE}/222/deregister").mock(return_value=ok())

    client.register_phone("222", "123456")
    client.deregister_phone("222")

    assert body_of(register.calls.last.request) == {
        "messaging_product": "whatsapp",
        "pin": "123456",
    }
    assert_customer_auth(register.calls.last.request)
    assert_customer_auth(deregister.calls.last.request)


# --- Messaging ---------------------------------------------------------------------------------


def test_send_message_adds_messaging_product(graph, client):
    route = graph.post(f"{BASE}/222/messages").mock(
        return_value=ok({"messages": [{"id": "wamid.X"}]})
    )
    message = {"to": "919800041207", "type": "text", "text": {"body": "Hi"}}

    assert client.send_message("222", message) == {"messages": [{"id": "wamid.X"}]}

    assert body_of(route.calls.last.request) == {**message, "messaging_product": "whatsapp"}
    assert_customer_auth(route.calls.last.request)


@pytest.mark.parametrize("typing", [False, True])
def test_mark_read(graph, client, typing):
    route = graph.post(f"{BASE}/222/messages").mock(return_value=ok())

    client.mark_read("222", "wamid.X", typing_indicator=typing)

    expected = {"messaging_product": "whatsapp", "status": "read", "message_id": "wamid.X"}
    if typing:
        expected["typing_indicator"] = {"type": "text"}
    assert body_of(route.calls.last.request) == expected


def test_upload_media_is_multipart(graph, client):
    route = graph.post(f"{BASE}/222/media").mock(return_value=ok({"id": "m1"}))

    assert client.upload_media(
        "222", content=b"PDFDATA", mime_type="application/pdf", filename="bill.pdf"
    ) == {"id": "m1"}

    request = route.calls.last.request
    assert request.headers["Content-Type"].startswith("multipart/form-data")
    content = request.content
    assert b'name="messaging_product"' in content
    assert b"whatsapp" in content
    assert b'filename="bill.pdf"' in content
    assert b"PDFDATA" in content
    assert_customer_auth(request)


def test_get_media(graph, client):
    route = graph.get(f"{BASE}/m1").mock(return_value=ok({"id": "m1", "url": "https://x"}))

    assert client.get_media("m1")["id"] == "m1"
    assert_customer_auth(route.calls.last.request)


def test_download_media_uses_bearer(graph, client):
    url = "https://lookaside.fbsbx.com/whatsapp_business/attachments/?mid=1"
    route = graph.get(url).mock(return_value=httpx.Response(200, content=b"bytes"))

    assert client.download_media(url) == b"bytes"
    assert route.calls.last.request.headers["Authorization"] == f"Bearer {TOKEN}"


def test_download_media_refuses_foreign_host(client):
    with pytest.raises(errors.InvalidParameterError):
        client.download_media("https://evil.example/file")


# --- Templates ---------------------------------------------------------------------------------


def test_list_templates(graph, client):
    route = graph.get(f"{BASE}/111/message_templates").mock(return_value=ok({"data": []}))

    client.list_templates("111", after="CUR", limit=25)

    params = route.calls.last.request.url.params
    assert params["after"] == "CUR"
    assert params["limit"] == "25"
    assert "quality_score" in params["fields"]
    assert_customer_auth(route.calls.last.request)


def test_create_template(graph, client):
    route = graph.post(f"{BASE}/111/message_templates").mock(
        return_value=ok({"id": "t1", "status": "PENDING", "category": "UTILITY"})
    )
    template = {"name": "order", "language": "en", "category": "UTILITY", "components": []}

    assert client.create_template("111", template)["id"] == "t1"
    assert body_of(route.calls.last.request) == template


@pytest.mark.parametrize("template_id", [None, "t1"])
def test_delete_template(graph, client, template_id):
    route = graph.delete(f"{BASE}/111/message_templates").mock(return_value=ok())

    client.delete_template("111", name="order", template_id=template_id)

    params = route.calls.last.request.url.params
    assert params["name"] == "order"
    assert params.get("hsm_id") == template_id


# --- Errors ------------------------------------------------------------------------------------


def meta_error(status, code, message="Meta says no"):
    return httpx.Response(
        status, json={"error": {"message": message, "type": "OAuthException", "code": code}}
    )


@pytest.mark.parametrize(
    ("response", "error_class", "retryable"),
    [
        (meta_error(401, 190, "Error validating access token"), errors.TokenInvalidError, False),
        (meta_error(400, 131047), errors.OutsideWindowError, False),
        (meta_error(400, 131050), errors.RecipientOptedOutError, False),
        (meta_error(429, 130429), errors.RateLimitedError, True),
        (meta_error(500, 1), errors.TransientError, True),
        (httpx.Response(502, text="<html>Bad gateway</html>"), errors.TransientError, True),
    ],
)
def test_error_mapping(graph, client, response, error_class, retryable):
    graph.post(f"{BASE}/222/messages").mock(return_value=response)

    with pytest.raises(error_class) as caught:
        client.send_message("222", {"to": "1", "type": "text"})

    assert caught.value.retryable is retryable
    assert caught.value.http_status == response.status_code
    assert TOKEN not in str(caught.value)


def test_retry_after_header_is_kept(graph, client):
    graph.get(f"{BASE}/222").mock(
        return_value=httpx.Response(
            429,
            headers={"Retry-After": "120"},
            json={"error": {"message": "Too many", "code": 4}},
        )
    )

    with pytest.raises(errors.RateLimitedError) as caught:
        client.get_phone_number("222")
    assert caught.value.retry_after == 120


@pytest.mark.parametrize("exception", [httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout])
def test_network_errors(graph, client, app_client, exception):
    graph.get(f"{BASE}/222").mock(side_effect=exception(f"failed for {TOKEN}"))
    graph.get(f"{BASE}/oauth/access_token").mock(side_effect=exception("client_secret=x"))

    with pytest.raises(errors.NetworkError) as caught:
        client.get_phone_number("222")
    assert caught.value.retryable is True
    assert TOKEN not in str(caught.value)
    assert caught.value.__cause__ is None

    with pytest.raises(errors.NetworkError) as caught:
        app_client.exchange_code("code")
    assert "test-app-secret" not in str(caught.value)


def test_customer_call_without_token_raises(app_client):
    with pytest.raises(errors.TokenInvalidError):
        app_client.get_waba("111")


def test_repr_hides_token(client):
    assert TOKEN not in repr(client)
    assert TOKEN not in str(client)


def test_default_http_client_uses_configured_timeout(settings):
    settings.META_GRAPH_TIMEOUT_SECONDS = 7.5

    client = HttpGraphClient(access_token=TOKEN)

    assert client._http.timeout.read == 7.5
