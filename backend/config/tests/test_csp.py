"""Content-Security-Policy headers from Django's CSP middleware (config/settings/base.py)."""

import re
import uuid

import pytest

CSP = "Content-Security-Policy"


def _directives(header: str) -> dict[str, list[str]]:
    parsed = {}
    for part in header.split(";"):
        name, *values = part.split()
        parsed[name] = values
    return parsed


def test_api_response_has_strict_policy(client):
    response = client.get("/api/v1/auth/me/")

    assert response.status_code == 401
    policy = _directives(response[CSP])
    assert policy["default-src"] == ["'none'"]
    assert policy["frame-ancestors"] == ["'none'"]
    assert policy["base-uri"] == ["'none'"]
    assert policy["script-src"] == ["'self'"]
    assert "'unsafe-inline'" not in response[CSP]


def test_health_probe_still_answers(client):
    assert client.get("/healthz/").status_code == 200


@pytest.mark.django_db
def test_admin_login_page_runs_under_policy(client):
    response = client.get("/admin/login/")

    assert response.status_code == 200
    policy = _directives(response[CSP])
    assert policy["script-src"] == ["'self'"]
    assert policy["style-src"] == ["'self'"]
    assert policy["frame-ancestors"] == ["'none'"]
    html = response.content.decode()
    # Every script and stylesheet the admin page uses is a same-origin file, so 'self' covers it.
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), "inline <script> would be blocked"
    assert "<style" not in html
    assert not re.search(r"\son[a-z]+=", html), "inline event handlers would be blocked"
    for url in re.findall(r'<(?:script|link)[^>]+(?:src|href)="([^"]+)"', html):
        assert url.startswith("/"), url


def test_api_docs_allow_swagger_assets_without_inline_script(client):
    response = client.get("/api/docs/")

    assert response.status_code == 200
    policy = _directives(response[CSP])
    assert policy["script-src"] == ["'self'", "https://cdn.jsdelivr.net"]
    assert policy["frame-ancestors"] == ["'none'"]
    html = response.content.decode()
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html)

    script = client.get("/api/docs/?script=")
    assert script.status_code == 200
    assert "SwaggerUIBundle" in script.content.decode()


@pytest.mark.django_db
def test_payment_return_page_keeps_its_own_policy(client):
    response = client.get(f"/pay/return/{uuid.uuid4()}/")

    assert response.status_code == 404
    assert response[CSP].startswith("default-src 'none'; style-src 'unsafe-inline'")
