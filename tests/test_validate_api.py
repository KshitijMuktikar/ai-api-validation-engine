"""Integration tests for HTTP API (rule-based path; LLM off for determinism)."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def _load_json(name: str) -> dict:
    with open(SAMPLES / name, encoding="utf-8") as f:
        return json.load(f)


def test_validate_valid_response(client: TestClient, pet_openapi: dict) -> None:
    body = {
        "openapi_spec": pet_openapi,
        "path": "/pets/1",
        "method": "get",
        "status_code": "200",
        "response_body": _load_json("sample_response_ok.json"),
        "use_llm_semantic": False,
    }
    r = client.post("/validate", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["validation_source"] == "rule_based"
    assert data["missing_fields"] == []
    assert data["type_mismatches"] == []
    assert data["unexpected_fields"] == []
    assert data["value_issues"] == []
    assert data["confidence_score"] == 1.0


def test_validate_type_mismatch_and_extra(client: TestClient, pet_openapi: dict) -> None:
    body = {
        "openapi_spec": pet_openapi,
        "path": "/pets/1",
        "method": "get",
        "status_code": "200",
        "response_body": _load_json("sample_response_bad.json"),
        "use_llm_semantic": False,
    }
    r = client.post("/validate", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["validation_source"] == "rule_based"
    assert len(data["type_mismatches"]) + len(data["value_issues"]) >= 1
    assert len(data["unexpected_fields"]) >= 1


def test_validate_malformed_json_body(client: TestClient) -> None:
    r = client.post(
        "/validate",
        content=b"{not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 422
    err = r.json()
    assert "error" in err or "detail" in err


def test_validate_openapi_path_not_found(client: TestClient, pet_openapi: dict) -> None:
    body = {
        "openapi_spec": pet_openapi,
        "path": "/does-not-exist",
        "method": "get",
        "status_code": "200",
        "response_body": {},
        "use_llm_semantic": False,
    }
    r = client.post("/validate", json=body)
    assert r.status_code == 400
    err = r.json()
    assert err.get("error")
