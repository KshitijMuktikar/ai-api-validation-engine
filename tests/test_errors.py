"""Tests for structured validation / client errors."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_missing_openapi_spec_and_url_returns_422(client: TestClient) -> None:
    r = client.post(
        "/validate",
        json={
            "path": "/x",
            "method": "get",
            "status_code": "200",
            "response_body": {},
            "use_llm_semantic": False,
        },
    )
    assert r.status_code == 422


def test_health_ok(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data
