"""Journey: a seller signs up, creates a workspace (trial starts), invites a teammate and connects
WhatsApp through Embedded Signup; the plan's number limit holds."""

import pytest
from django.core import mail

from apps.billing.models import Subscription
from apps.tenants.models import Membership
from apps.whatsapp.models import PhoneNumber, WhatsAppBusinessAccount

from .conftest import PHONE_NUMBER_ID, WABA_ID
from .test_journey_support import (
    INVITE_TOKEN_RE,
    PASSWORD,
    Api,
    connect_whatsapp,
    create_workspace,
    error,
    invite_and_join,
    ok,
    results,
    sign_up,
)

pytest_plugins = ["tests.test_journey_support"]
pytestmark = pytest.mark.django_db


def test_seller_onboarding_from_sign_up_to_a_connected_number(run_on_commit, fake_graph):
    owner = sign_up(run_on_commit, "ravi@sharmasweets.in", "Ravi Sharma")

    # Wrong password is refused; the real one works (sign_up already logged in once).
    refused = Api(run_on_commit).post(
        "/api/v1/auth/token/", {"email": "ravi@sharmasweets.in", "password": PASSWORD + "x"}
    )
    assert refused.status_code == 401, refused.content
    me = ok(owner.get("/api/v1/auth/me/"))
    assert (me["full_name"], me["memberships"]) == ("Ravi Sharma", [])

    workspace_id = create_workspace(owner, "Sharma Sweets")
    me = ok(owner.get("/api/v1/auth/me/"))
    assert [(m["workspace_id"], m["role"]) for m in me["memberships"]] == [(workspace_id, "owner")]

    # The trial starts from WorkspaceCreated, before anyone looks at billing.
    subscription = Subscription.objects.get(workspace_id=workspace_id)
    assert (subscription.status, subscription.plan_id) == ("trialing", "growth")
    body = ok(owner.get("/api/v1/billing/subscription/"))
    assert (body["status"], body["plan"]["id"]) == ("trialing", "growth")
    assert body["trial_ends_at"]

    # Invite an agent; she signs up from the emailed link and joins.
    agent = invite_and_join(
        owner, run_on_commit, email="meera@sharmasweets.in", full_name="Meera", role="agent"
    )
    members = results(owner.get("/api/v1/workspaces/members/"))
    assert sorted((m["user"]["email"], m["role"]) for m in members) == [
        ("meera@sharmasweets.in", "agent"),
        ("ravi@sharmasweets.in", "owner"),
    ]
    error(agent.get("/api/v1/workspaces/invitations/"), 403, "insufficient_role")
    usage = {m["key"]: m for m in ok(owner.get("/api/v1/billing/usage/"))["metrics"]}
    assert (usage["members"]["used"], usage["members"]["limit"]) == (2, 5)

    # Agents can't connect WhatsApp; the owner can.
    error(connect_whatsapp(agent, fake_graph), 403, "insufficient_role")
    waba = ok(connect_whatsapp(owner, fake_graph), 201)
    assert waba["waba_id"] == WABA_ID
    assert waba["status"] == "pending"  # onboarding finishes in a task after the response
    [waba] = results(owner.get("/api/v1/whatsapp/accounts/"))
    assert (waba["status"], waba["onboarding_status"]) == ("active", "completed")
    assert WABA_ID in fake_graph.subscribed_waba_ids
    assert PHONE_NUMBER_ID in fake_graph.registered_pins
    assert "access_token" not in str(waba)

    [phone] = results(agent.get("/api/v1/whatsapp/phone-numbers/"))
    assert phone["phone_number_id"] == PHONE_NUMBER_ID
    assert phone["registration_status"] == "registered"
    assert phone["is_default"] is True
    assert "pin" not in phone

    # Reconnecting the same account is never blocked by the quota.
    ok(connect_whatsapp(owner, fake_graph, code="signup-code-2"), 201)
    assert PhoneNumber.objects.filter(workspace_id=workspace_id).count() == 1

    # Growth allows 2 numbers: a second account with two more numbers is refused before storing.
    refused = connect_whatsapp(
        owner,
        fake_graph,
        code="signup-code-3",
        waba_id="200000000000001",
        numbers=(("200000000000011", "+91 98000 00011"), ("200000000000012", "+91 98000 00012")),
    )
    details = error(refused, 409, "quota_exceeded")["details"]
    assert details == {"metric": "whatsapp_numbers", "limit": 2, "used": 1}
    assert not WhatsAppBusinessAccount.objects.filter(waba_id="200000000000001").exists()

    # One more number fits.
    ok(
        connect_whatsapp(
            owner,
            fake_graph,
            code="signup-code-4",
            waba_id="200000000000003",
            numbers=(("200000000000031", "+91 98000 00031"),),
        ),
        201,
    )
    numbers = results(owner.get("/api/v1/whatsapp/phone-numbers/"))
    assert len(numbers) == 2
    assert [n["phone_number_id"] for n in numbers if n["is_default"]] == [PHONE_NUMBER_ID]

    # And a third doesn't.
    error(
        connect_whatsapp(
            owner,
            fake_graph,
            code="signup-code-5",
            waba_id="200000000000002",
            numbers=(("200000000000021", "+91 98000 00021"),),
        ),
        409,
        "quota_exceeded",
    )
    usage = {m["key"]: m for m in ok(owner.get("/api/v1/billing/usage/"))["metrics"]}
    assert (usage["whatsapp_numbers"]["used"], usage["whatsapp_numbers"]["limit"]) == (2, 2)


def test_member_limit_counts_open_invitations_and_is_rechecked_on_accept(run_on_commit, fake_graph):
    owner = sign_up(run_on_commit, "ravi@sharmasweets.in", "Ravi Sharma")
    workspace_id = create_workspace(owner, "Sharma Sweets")
    invite = "/api/v1/workspaces/invitations/"

    # During the Growth trial (5 members) two invitations go out.
    mail.outbox.clear()
    for email in ("a@sharmasweets.in", "b@sharmasweets.in"):
        ok(owner.post(invite, {"email": email, "role": "agent"}), 201)
    tokens = {m.to[0]: INVITE_TOKEN_RE.search(m.body).group(1) for m in mail.outbox}

    # The seller picks Starter (2 members): open invitations now fill the plan.
    Subscription.objects.filter(workspace_id=workspace_id).update(plan_id="starter")
    refused = owner.post(invite, {"email": "c@sharmasweets.in", "role": "agent"})
    assert error(refused, 409, "quota_exceeded")["details"]["metric"] == "members"
    # Re-inviting the same email replaces the invitation instead of taking another seat, but
    # the other open invitation still counts.
    refused = owner.post(invite, {"email": "a@sharmasweets.in", "role": "admin"})
    assert error(refused, 409, "quota_exceeded")["details"] == {
        "metric": "members",
        "limit": 2,
        "used": 1,
    }

    # Acceptance re-checks the limit: the first invitee fits, the second doesn't.
    first = sign_up(run_on_commit, "a@sharmasweets.in", "Asha")
    ok(first.post(f"{invite}accept/", {"token": tokens["a@sharmasweets.in"]}))
    second = sign_up(run_on_commit, "b@sharmasweets.in", "Bala")
    refused = second.post(f"{invite}accept/", {"token": tokens["b@sharmasweets.in"]})
    assert error(refused, 409, "quota_exceeded")["details"]["metric"] == "members"
    assert Membership.objects.filter(workspace_id=workspace_id).count() == 2
    assert ok(second.get("/api/v1/auth/me/"))["memberships"] == []

    # Revoking the stuck invitation frees nothing (the plan is full) but clears the list.
    [stuck] = results(owner.get(invite))
    ok(owner.delete(f"{invite}{stuck['id']}/"), 204)
    assert results(owner.get(invite)) == []
