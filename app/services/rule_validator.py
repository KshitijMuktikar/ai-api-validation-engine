"""
Deterministic JSON Schema validation (primary / rule-based layer).

Uses ``jsonschema`` with a validator chosen from the schema when possible.
Maps errors to missing fields, type mismatches, unexpected properties, and value issues.
"""
from __future__ import annotations

import re
from typing import Any

from jsonschema import ValidationError, validators

from app.logging_config import get_logger
from app.models.schemas import ValidationResult, ValidationSource

logger = get_logger(__name__)


def _json_pointer_path(error: ValidationError) -> str:
    parts = list(error.absolute_path) if error.absolute_path else list(error.path)
    if not parts:
        return "/"
    return "/" + "/".join(str(p) for p in parts)


def _classify(error: ValidationError) -> tuple[str, str]:
    """
    Return (category, formatted_line) where category is one of
    missing | type | unexpected | value.
    """
    path = _json_pointer_path(error)
    msg = (error.message or "").strip()
    validator = error.validator

    # Required properties (message shape: 'name' is a required property)
    if validator == "required" or "is a required property" in msg:
        m = re.search(r"'([^']+)' is a required property", msg)
        if m:
            prop = m.group(1)
            sub = f"{path.rstrip('/')}/{prop}" if path != "/" else f"/{prop}"
            return "missing", f"{sub}: required property missing"

    # Additional properties
    if validator == "additionalProperties" or "Additional properties are not allowed" in msg:
        m = re.search(r"\('([^']+)'\)", msg)
        prop = m.group(1) if m else None
        if prop:
            sub = f"{path.rstrip('/')}/{prop}" if path != "/" else f"/{prop}"
            return "unexpected", f"{sub}: additional property not allowed by schema"
        return "unexpected", f"{path}: {msg}"

    # Type
    if validator == "type" or "is not of type" in msg:
        return "type", f"{path}: {msg}"

    # Enum / format / bounds
    if validator in ("enum", "format", "minimum", "maximum", "minLength", "maxLength", "pattern"):
        return "value", f"{path}: {msg}"

    # Default bucket
    return "value", f"{path}: {msg}"


def validate_with_rules(schema: dict[str, Any], instance: Any) -> ValidationResult:
    """
    Validate ``instance`` against JSON ``schema``; return structured issues.

    Does not call external services. For OpenAPI-flavored schemas, some edge cases
    may surface as generic ``value_issues`` — the LLM layer can refine semantics.
    """
    missing_fields: list[str] = []
    type_mismatches: list[str] = []
    unexpected_fields: list[str] = []
    value_issues: list[str] = []

    ValidatorCls = validators.validator_for(schema)
    try:
        validator = ValidatorCls(schema)
    except Exception as e:
        logger.warning("Could not build JSON Schema validator: %s", e)
        return ValidationResult(
            missing_fields=[],
            type_mismatches=[],
            unexpected_fields=[],
            value_issues=[f"Rule validator could not compile schema: {e}"],
            confidence_score=1.0,
            validation_source=ValidationSource.RULE_BASED,
            notes=None,
        )

    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))

    if not errors:
        return ValidationResult(
            missing_fields=[],
            type_mismatches=[],
            unexpected_fields=[],
            value_issues=[],
            confidence_score=1.0,
            validation_source=ValidationSource.RULE_BASED,
            notes=None,
        )

    seen: set[str] = set()
    for err in errors:
        # Prefer a single representative error per path for noise reduction
        cat, line = _classify(err)
        if line in seen:
            continue
        seen.add(line)
        if cat == "missing":
            missing_fields.append(line)
        elif cat == "type":
            type_mismatches.append(line)
        elif cat == "unexpected":
            unexpected_fields.append(line)
        else:
            value_issues.append(line)

    return ValidationResult(
        missing_fields=missing_fields,
        type_mismatches=type_mismatches,
        unexpected_fields=unexpected_fields,
        value_issues=value_issues,
        confidence_score=1.0,
        validation_source=ValidationSource.RULE_BASED,
        notes=None,
    )
