"""ResendEmailBackend against httpx.MockTransport (never the network)."""

import json
import logging

import httpx
import pytest
from django.core.mail import EmailMessage, EmailMultiAlternatives

from common.mail_backends import RESEND_API_URL, EmailSendError, ResendEmailBackend

API_KEY = "re_test_secret_key_123"


class Recorder:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.responses.pop(0) if self.responses else httpx.Response(200)
        if isinstance(response, Exception):
            raise response
        return response

    def json(self, index=0) -> dict:
        return json.loads(self.requests[index].content)


def backend(recorder, **kwargs):
    return ResendEmailBackend(
        api_key=API_KEY, transport=httpx.MockTransport(recorder), timeout=5, **kwargs
    )


def message(**kwargs):
    defaults = {
        "subject": "Hello",
        "body": "Plain body",
        "from_email": "UpChatz <no-reply@upchatz.com>",
        "to": ["asha@example.com"],
    }
    return EmailMultiAlternatives(**{**defaults, **kwargs})


def test_posts_the_resend_payload_with_html_alternative_and_idempotency_header():
    recorder = Recorder(httpx.Response(200, json={"id": "abc"}))
    email = message(
        cc=["cc@example.com"],
        bcc=["bcc@example.com"],
        reply_to=["support@upchatz.com"],
        headers={"Idempotency-Key": "verify:1:abc", "X-Entity-Ref-ID": "42"},
    )
    email.attach_alternative("<p>HTML body</p>", "text/html")

    assert backend(recorder).send_messages([email]) == 1

    [request] = recorder.requests
    assert str(request.url) == RESEND_API_URL
    assert request.method == "POST"
    assert request.headers["Authorization"] == f"Bearer {API_KEY}"
    assert request.headers["Idempotency-Key"] == "verify:1:abc"
    assert recorder.json() == {
        "from": "UpChatz <no-reply@upchatz.com>",
        "to": ["asha@example.com"],
        "cc": ["cc@example.com"],
        "bcc": ["bcc@example.com"],
        "reply_to": ["support@upchatz.com"],
        "subject": "Hello",
        "text": "Plain body",
        "html": "<p>HTML body</p>",
        "headers": {"X-Entity-Ref-ID": "42"},
    }


def test_plain_message_has_no_optional_fields():
    recorder = Recorder()

    assert backend(recorder).send_messages([EmailMessage("S", "B", "a@b.co", ["x@example.com"])])

    assert recorder.json() == {
        "from": "a@b.co",
        "to": ["x@example.com"],
        "subject": "S",
        "text": "B",
    }
    assert "Idempotency-Key" not in recorder.requests[0].headers


def test_counts_each_message_sent():
    recorder = Recorder()
    assert backend(recorder).send_messages([message(), message(), message(to=[])]) == 2
    assert backend(recorder).send_messages([]) == 0


@pytest.mark.parametrize(
    ("response", "retryable"),
    [
        (httpx.Response(429, json={"name": "rate_limit_exceeded", "message": "Slow down"}), True),
        (httpx.Response(500, json={"name": "internal_server_error", "message": "Oops"}), True),
        (httpx.Response(503, text="unavailable"), True),
        (httpx.Response(422, json={"name": "validation_error", "message": "Bad to"}), False),
        (httpx.Response(401, json={"name": "missing_api_key", "message": "No key"}), False),
        (httpx.ReadTimeout("timed out"), True),
        (httpx.ConnectError("refused"), True),
    ],
)
def test_failures_raise_with_retryable_classification(response, retryable):
    with pytest.raises(EmailSendError) as info:
        backend(Recorder(response)).send_messages([message()])

    assert info.value.retryable is retryable


def test_fail_silently_returns_what_was_sent_so_far():
    recorder = Recorder(httpx.Response(200), httpx.Response(500), httpx.Response(200))

    sent = backend(recorder, fail_silently=True).send_messages([message(), message(), message()])

    assert sent == 1
    assert len(recorder.requests) == 2


def test_missing_api_key_is_not_retryable():
    with pytest.raises(EmailSendError) as info:
        ResendEmailBackend(api_key="").send_messages([message()])
    assert info.value.retryable is False


def test_logs_status_and_error_name_but_never_the_key_or_body(caplog):
    recorder = Recorder(httpx.Response(422, json={"name": "validation_error", "message": "bad"}))
    email = message(body="secret reset link https://x/?token=abc")
    email.attach_alternative("<p>secret html</p>", "text/html")

    with caplog.at_level(logging.DEBUG), pytest.raises(EmailSendError):
        backend(recorder).send_messages([email])

    logged = caplog.text
    assert "422" in logged
    assert "validation_error" in logged
    assert API_KEY not in logged
    assert "secret" not in logged
    assert "token=abc" not in logged


def test_selected_by_email_backend_setting(settings):
    from django.core.mail import get_connection

    settings.RESEND_API_KEY = API_KEY
    settings.RESEND_TIMEOUT = 7
    connection = get_connection("common.mail_backends.ResendEmailBackend")

    assert isinstance(connection, ResendEmailBackend)
    assert (connection.api_key, connection.timeout) == (API_KEY, 7)
