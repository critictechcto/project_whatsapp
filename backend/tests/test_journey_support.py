"""Shared setup for the seller journey tests (``test_journey_*.py``; this module holds no tests).

Journeys act like real clients: a seller registers and logs in through ``/api/v1/auth/``, works
through the public REST API with a JWT and the ``X-Workspace-ID`` header, and customers act only
through signed Meta webhooks. Every API call runs the callbacks it queues on commit, so events,
realtime frames and (eager) Celery tasks play out as they would after a real request.

Journey modules load the fixtures with ``pytest_plugins = ["tests.test_journey_support"]``.
"""

import itertools
import re
import time

import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.message_templates.factories import standard_components
from common.tenancy import WORKSPACE_HEADER

from .conftest import (
    CUSTOMER_WA_ID,
    DISPLAY_PHONE_NUMBER,
    PHONE_NUMBER_ID,
    WABA_ID,
    inbound_text,
    messages_payload,
)

PASSWORD = "Rangoli-Lamp-2026!"
_WORKSPACE_META_KEY = "HTTP_" + WORKSPACE_HEADER.upper().replace("-", "_")
_wamids = itertools.count(1)
INVITE_TOKEN_RE = re.compile(r"token=([A-Za-z0-9_\-]+)")


class Api:
    """A dashboard session: JWT plus workspace header. Each call runs its on-commit callbacks."""

    def __init__(self, run_on_commit, access: str | None = None, workspace_id=None):
        self.run_on_commit = run_on_commit
        self.client = APIClient()
        self.access = access
        self.workspace_id = workspace_id
        self._apply()

    def _apply(self) -> None:
        credentials = {}
        if self.access:
            credentials["HTTP_AUTHORIZATION"] = f"Bearer {self.access}"
        if self.workspace_id:
            credentials[_WORKSPACE_META_KEY] = str(self.workspace_id)
        self.client.credentials(**credentials)

    def use_workspace(self, workspace_id) -> "Api":
        self.workspace_id = workspace_id
        self._apply()
        return self

    def _call(self, method: str, url: str, data=None, **kwargs):
        if data is not None and "format" not in kwargs:
            kwargs["format"] = "json"
        with self.run_on_commit():
            return getattr(self.client, method)(url, data, **kwargs)

    def get(self, url, data=None, **kwargs):
        with self.run_on_commit():
            return self.client.get(url, data, **kwargs)

    def post(self, url, data=None, **kwargs):
        return self._call("post", url, data, **kwargs)

    def patch(self, url, data=None, **kwargs):
        return self._call("patch", url, data, **kwargs)

    def delete(self, url, **kwargs):
        with self.run_on_commit():
            return self.client.delete(url, **kwargs)


def ok(response, status: int = 200):
    assert response.status_code == status, (response.status_code, response.content[:2000])
    return response.json() if response.content else None


def error(response, status: int, code: str) -> dict:
    assert response.status_code == status, (response.status_code, response.content[:2000])
    body = response.json()["error"]
    assert body["code"] == code, body
    return body


def results(response) -> list[dict]:
    return ok(response)["results"]


def next_wamid(prefix: str = "JOURNEY") -> str:
    return f"wamid.{prefix}{next(_wamids):06d}"


def now_ts() -> int:
    return int(time.time())


# --- Accounts and workspaces --------------------------------------------------------------------


def sign_up(run_on_commit, email: str, full_name: str) -> Api:
    """Register, then log in with the password (as the dashboard does) and return the session."""
    anonymous = Api(run_on_commit)
    registered = ok(
        anonymous.post(
            "/api/v1/auth/register/",
            {"email": email, "password": PASSWORD, "full_name": full_name},
        ),
        201,
    )
    assert registered["user"]["email"] == email
    return log_in(run_on_commit, email)


def log_in(run_on_commit, email: str) -> Api:
    tokens = ok(
        Api(run_on_commit).post("/api/v1/auth/token/", {"email": email, "password": PASSWORD})
    )
    api = Api(run_on_commit, access=tokens["access"])
    api.email = email
    return api


def log_in_again(*sessions: Api) -> None:
    """Access tokens last minutes; after moving the clock, sessions log in again in place."""
    for session in sessions:
        fresh = log_in(session.run_on_commit, session.email)
        session.access = fresh.access
        session._apply()


def create_workspace(api: Api, name: str, time_zone: str = "Asia/Kolkata") -> str:
    body = ok(api.post("/api/v1/workspaces/", {"name": name, "time_zone": time_zone}), 201)
    api.use_workspace(body["id"])
    return body["id"]


def invite_and_join(owner: Api, run_on_commit, *, email: str, full_name: str, role: str) -> Api:
    """Invite ``email``; the invitee signs up, follows the emailed link and joins."""
    mail.outbox.clear()
    ok(owner.post("/api/v1/workspaces/invitations/", {"email": email, "role": role}), 201)
    [invite] = [m for m in mail.outbox if email in m.to]
    token = INVITE_TOKEN_RE.search(invite.body).group(1)
    member = sign_up(run_on_commit, email, full_name)
    joined = ok(member.post("/api/v1/workspaces/invitations/accept/", {"token": token}))
    assert joined["role"] == role
    return member.use_workspace(owner.workspace_id)


def connect_whatsapp(
    api: Api,
    fake_graph,
    *,
    code: str = "signup-code-1",
    waba_id: str = WABA_ID,
    numbers: tuple[tuple[str, str], ...] = ((PHONE_NUMBER_ID, DISPLAY_PHONE_NUMBER),),
):
    """Embedded Signup finished in the browser; the dashboard posts the code and ids."""
    fake_graph.add_waba(waba_id, name="Sharma Sweets")
    for phone_id, display in numbers:
        fake_graph.add_phone_number(waba_id, phone_id, display_phone_number=display)
    fake_graph.add_signup(code, waba_id=waba_id)
    return api.post(
        "/api/v1/whatsapp/embedded-signup/",
        {"code": code, "waba_id": waba_id, "phone_number_id": numbers[0][0]},
    )


# --- Templates ----------------------------------------------------------------------------------


def template_status_webhook(meta_template_id: str, name: str, event: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": WABA_ID,
                "changes": [
                    {
                        "field": "message_template_status_update",
                        "value": {
                            "event": event,
                            "message_template_id": int(meta_template_id),
                            "message_template_name": name,
                            "message_template_language": "en",
                            "reason": "NONE",
                        },
                    }
                ],
            }
        ],
    }


def approved_template(
    api: Api, deliver, *, name: str, body: str, category: str = "UTILITY"
) -> dict:
    """Create a template, submit it to Meta and deliver Meta's approval webhook."""
    [waba] = [w for w in results(api.get("/api/v1/whatsapp/accounts/")) if w["waba_id"] == WABA_ID]
    draft = ok(
        api.post(
            "/api/v1/templates/",
            {
                "waba": waba["id"],
                "name": name,
                "language": "en",
                "category": category,
                "components": standard_components(body),
            },
        ),
        201,
    )
    submitted = ok(api.post(f"/api/v1/templates/{draft['id']}/submit/"))
    deliver(template_status_webhook(submitted["meta_template_id"], name, "APPROVED"))
    approved = ok(api.get(f"/api/v1/templates/{draft['id']}/"))
    assert approved["status"] == "APPROVED", approved
    return approved


# --- Customers ----------------------------------------------------------------------------------


class Customer:
    """A WhatsApp user messaging the seller's number through signed Meta webhooks."""

    def __init__(self, deliver, wa_id: str = CUSTOMER_WA_ID, name: str = "Priya Sharma"):
        self.deliver, self.wa_id, self.name = deliver, wa_id, name

    def says(self, text: str, *, wamid: str | None = None, timestamp: int | None = None) -> dict:
        payload = inbound_text(
            text,
            wamid or next_wamid(),
            timestamp or now_ts(),
            wa_id=self.wa_id,
            name=self.name,
        )
        self.deliver(payload)
        return payload

    def taps_template_button(self, payload: str, text: str) -> dict:
        body = messages_payload(
            contacts=[{"profile": {"name": self.name}, "wa_id": self.wa_id}],
            messages=[
                {
                    "from": self.wa_id,
                    "id": next_wamid(),
                    "timestamp": str(now_ts()),
                    "type": "button",
                    "button": {"payload": payload, "text": text},
                }
            ],
        )
        self.deliver(body)
        return body


# --- Fixtures -----------------------------------------------------------------------------------


@pytest.fixture
def run_on_commit(django_capture_on_commit_callbacks):
    return lambda: django_capture_on_commit_callbacks(execute=True)


@pytest.fixture
def seller_api(run_on_commit, fake_graph) -> Api:
    """An owner who signed up, created "Sharma Sweets" and connected the store number."""
    api = sign_up(run_on_commit, "ravi@sharmasweets.in", "Ravi Sharma")
    create_workspace(api, "Sharma Sweets")
    ok(connect_whatsapp(api, fake_graph), 201)
    return api


@pytest.fixture
def seller_number_id(seller_api) -> str:
    [phone] = results(seller_api.get("/api/v1/whatsapp/phone-numbers/"))
    return phone["id"]


@pytest.fixture
def customer(deliver_meta) -> Customer:
    return Customer(deliver_meta)
