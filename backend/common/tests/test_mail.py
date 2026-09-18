import pickle
import smtplib

import pytest
from django.core import mail

from common.mail import (
    is_retryable_email_error,
    retry_countdown,
    send_or_retry,
    send_templated_email,
)
from common.mail_backends import EmailSendError


class FakeTask:
    def __init__(self, retries=0):
        self.request = type("Request", (), {"retries": retries})()
        self.retry_calls = []

    def retry(self, **kwargs):
        self.retry_calls.append(kwargs)
        return RuntimeError("retry requested")


def test_send_or_retry_retries_with_backoff_and_a_cap_of_five(monkeypatch):
    error = EmailSendError("Resend returned 503", retryable=True)

    def fail(**kwargs):
        raise error

    monkeypatch.setattr("common.mail.send_templated_email", fail)
    task = FakeTask(retries=2)

    with pytest.raises(RuntimeError):
        send_or_retry(task, retry_kwargs={"user_id": "u", "token": "t"}, to="a@example.com")

    assert task.retry_calls == [
        {
            "exc": error,
            "countdown": 120,
            "max_retries": 5,
            "args": (),
            "kwargs": {"user_id": "u", "token": "t"},
        }
    ]


def test_send_or_retry_raises_permanent_errors(monkeypatch):
    error = EmailSendError("Resend returned 422", retryable=False)

    def fail(**kwargs):
        raise error

    monkeypatch.setattr("common.mail.send_templated_email", fail)
    task = FakeTask()

    with pytest.raises(EmailSendError) as info:
        send_or_retry(task, to="a@example.com")

    assert info.value is error
    assert task.retry_calls == []


def test_email_send_error_survives_pickling():
    # Round-trips our own object in memory (as Celery does for results); no untrusted data.
    dumped = pickle.dumps(EmailSendError("x", retryable=True, status_code=503))
    restored = pickle.loads(dumped)  # noqa: S301
    assert (str(restored), restored.retryable, restored.status_code) == ("x", True, 503)


def test_templated_email_has_text_and_html_parts(settings):
    settings.DEFAULT_FROM_EMAIL = "UpChatz <no-reply@upchatz.com>"
    settings.EMAIL_REPLY_TO = "support@upchatz.com"

    send_templated_email(
        to="asha@example.com",
        template="invitation",
        context={
            "inviter": "Ravi <Sharma>",
            "workspace": "Sharma & Sons",
            "role": "agent",
            "email": "asha@example.com",
            "link": "https://app.example/app/invitations/accept?token=abc&x=1",
            "expires_on": "01 Jan 2027",
        },
        idempotency_key="invite:1",
    )

    [message] = mail.outbox
    assert message.subject == "Ravi <Sharma> invited you to Sharma & Sons on UpChatz"
    assert message.from_email == "UpChatz <no-reply@upchatz.com>"
    assert message.reply_to == ["support@upchatz.com"]
    assert message.extra_headers["Idempotency-Key"] == "invite:1"
    # Plain text keeps the raw link and unescaped names.
    assert "https://app.example/app/invitations/accept?token=abc&x=1" in message.body
    assert "Ravi <Sharma> invited you to join Sharma & Sons on UpChatz as agent." in message.body
    [(html, mimetype)] = message.alternatives
    assert mimetype == "text/html"
    # HTML escapes user-supplied names and keeps the shared layout.
    assert "Ravi &lt;Sharma&gt;" in html
    assert "Sharma &amp; Sons" in html
    assert "Accept invitation" in html
    assert "max-width:560px" in html
    assert "support@upchatz.com" in html
    assert "<script" not in html and "<img" not in html


def test_retryable_classification():
    assert is_retryable_email_error(EmailSendError("x", retryable=True))
    assert not is_retryable_email_error(EmailSendError("x", retryable=False))
    assert is_retryable_email_error(smtplib.SMTPServerDisconnected())
    assert is_retryable_email_error(smtplib.SMTPResponseException(451, b"try later"))
    assert not is_retryable_email_error(smtplib.SMTPResponseException(550, b"no such user"))
    assert is_retryable_email_error(TimeoutError())
    assert not is_retryable_email_error(ValueError())


def test_backoff_grows_and_is_capped():
    assert [retry_countdown(n) for n in range(4)] == [30, 60, 120, 240]
    assert retry_countdown(20) == 30 * 60
