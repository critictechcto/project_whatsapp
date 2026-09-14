import pytest
from django.core.management import call_command
from django.db import OperationalError
from drf_spectacular.drainage import reset_generator_stats

import common.views

OPENAPI_JSON = "application/vnd.oai.openapi+json"


def test_healthz(client):
    response = client.get("/healthz/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_readyz_with_database(client):
    response = client.get("/readyz/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_reports_unavailable_database(client, monkeypatch):
    class BrokenConnection:
        def cursor(self):
            raise OperationalError("database is down")

    monkeypatch.setattr(common.views, "connection", BrokenConnection())

    response = client.get("/readyz/")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_schema_is_an_openapi_document(client):
    response = client.get("/api/schema/", HTTP_ACCEPT=OPENAPI_JSON)

    assert response.status_code == 200
    document = response.json()
    assert document["openapi"].startswith("3.")
    assert document["info"]["title"] == "project_whatsapp API"
    assert document["paths"]
    assert all(route.startswith("/api/v1/") for route in document["paths"])


def test_schema_documents_workspace_header(client):
    document = client.get("/api/schema/", HTTP_ACCEPT=OPENAPI_JSON).json()

    parameters = [
        parameter
        for item in document["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict)
        for parameter in operation.get("parameters", [])
    ]
    assert any(
        parameter["name"] == "X-Workspace-ID" and parameter["in"] == "header"
        for parameter in parameters
    )


def test_api_docs(client):
    response = client.get("/api/docs/")

    assert response.status_code == 200
    assert b"swagger" in response.content.lower()


def test_openapi_schema_generates_without_warnings(tmp_path):
    """Same gate as CI: any app that adds a schema warning fails the test suite."""
    reset_generator_stats()
    output = tmp_path / "schema.yml"

    call_command("spectacular", "--validate", "--fail-on-warn", "--file", str(output))

    assert output.read_text(encoding="utf-8").startswith("openapi:")
