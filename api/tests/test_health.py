"""``GET /api/health``."""

from __future__ import annotations

from pathlib import Path


def test_health_returns_ok(client) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == "0.1.0"
    assert Path(payload["state_dir"]).is_absolute()


def test_health_state_dir_is_the_real_one(client, state_dir: Path) -> None:
    response = client.get("/api/health")
    assert response.json()["state_dir"] == str(state_dir)


def test_docs_serves_swagger(client) -> None:
    response = client.get("/api/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.lower()


def test_openapi_schema_is_served(client) -> None:
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Indeed Job Scraper API"
    for path in (
        "/api/health",
        "/api/jobs",
        "/api/jobs/facets",
        "/api/jobs/{short_id}",
        "/api/session",
        "/api/runs",
        "/api/applications",
        "/api/applications/summary",
        "/api/messages",
    ):
        assert path in schema["paths"], path


def test_no_write_methods_are_exposed(client) -> None:
    """The contract has no POST/PUT/DELETE endpoints."""
    schema = client.get("/api/openapi.json").json()
    for path, operations in schema["paths"].items():
        for method in operations:
            assert method in {"get", "head", "options"}, f"{method.upper()} {path}"
