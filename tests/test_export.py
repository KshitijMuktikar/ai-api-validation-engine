"""Export endpoint smoke tests."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient


def test_export_json_attachment(client: TestClient, pet_openapi: dict) -> None:
    body = {
        "validation_request": {
            "openapi_spec": pet_openapi,
            "path": "/pets/1",
            "method": "get",
            "status_code": "200",
            "response_body": {"id": 1, "name": "Buddy", "status": "available"},
            "use_llm_semantic": False,
        },
        "format": "json",
    }
    r = client.post("/validate/export", json=body)
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")
    data = json.loads(r.text)
    assert "validation_source" in data
    assert data["validation_source"] == "rule_based"


def test_export_csv_attachment(client: TestClient, pet_openapi: dict) -> None:
    body = {
        "validation_request": {
            "openapi_spec": pet_openapi,
            "path": "/pets/1",
            "method": "get",
            "status_code": "200",
            "response_body": {"id": 1, "name": "Buddy", "status": "available"},
            "use_llm_semantic": False,
        },
        "format": "csv",
    }
    r = client.post("/validate/export", json=body)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("text/csv")
    assert "missing_fields" in r.text
