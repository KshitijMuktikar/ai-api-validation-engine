"""Unit tests for the deterministic JSON Schema (rule-based) validator."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.schemas import ValidationSource
from app.services.rule_validator import validate_with_rules

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


@pytest.fixture
def pet_schema() -> dict:
    """Resolved Pet schema (inline, no $ref) for direct rule validation."""
    with open(SAMPLES / "openapi_pet.json", encoding="utf-8") as spec_file:
        spec = json.load(spec_file)
    pet = spec["components"]["schemas"]["Pet"]
    assert isinstance(pet, dict)
    return pet


def test_rule_validator_valid_response(pet_schema: dict) -> None:
    with open(SAMPLES / "sample_response_ok.json", encoding="utf-8") as f:
        body = json.load(f)
    r = validate_with_rules(pet_schema, body)
    assert r.validation_source == ValidationSource.RULE_BASED
    assert r.missing_fields == []
    assert r.type_mismatches == []
    assert r.unexpected_fields == []
    assert r.value_issues == []
    assert r.confidence_score == 1.0


def test_rule_validator_missing_fields(pet_schema: dict) -> None:
    body = {"id": 1, "status": "available"}  # missing name
    r = validate_with_rules(pet_schema, body)
    assert any("name" in m for m in r.missing_fields)
    assert r.validation_source == ValidationSource.RULE_BASED


def test_rule_validator_type_mismatch_and_extra(pet_schema: dict) -> None:
    with open(SAMPLES / "sample_response_bad.json", encoding="utf-8") as f:
        body = json.load(f)
    r = validate_with_rules(pet_schema, body)
    assert r.type_mismatches or r.value_issues  # id wrong type surfaces as type or value
    assert any("extra" in u.lower() or "additional" in u.lower() for u in r.unexpected_fields) or any(
        "extraField" in v for v in r.unexpected_fields
    )
