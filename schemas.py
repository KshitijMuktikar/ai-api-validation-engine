"""
Pydantic models for API request and response contracts.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ValidateRequest(BaseModel):
    """Body for POST /validate."""

    # OpenAPI 3.x document as a JSON-serializable dict (preferred)
    openapi_spec: Optional[dict[str, Any]] = Field(
        default=None,
        description="Full OpenAPI 3.x specification as JSON object.",
    )
    # Alternative: fetch spec from this URL (HTTPS)
    openapi_spec_url: Optional[str] = Field(
        default=None,
        description="URL to fetch OpenAPI JSON (e.g. https://petstore.swagger.io/v2/swagger.json for OAS2, or a raw OAS3 URL).",
    )
    path: str = Field(..., description="API path as in the spec, e.g. /pets/1 or /users/{id}")
    method: str = Field(..., description="HTTP method in lowercase, e.g. get, post")
    status_code: str = Field(
        default="200",
        description="Response status code key as in OpenAPI, e.g. 200, default, 201",
    )
    response_body: Any = Field(
        ...,
        description="Actual JSON response body to validate (object, array, or primitive).",
    )
    include_schema_in_prompt: bool = Field(
        default=True,
        description="If true, include resolved JSON Schema in the LLM prompt for precision.",
    )


class ValidationResult(BaseModel):
    """Structured validation output from the LLM (and optional pre-checks)."""

    missing_fields: list[str] = Field(
        default_factory=list,
        description="Paths to required fields present in the spec but missing in the response.",
    )
    type_mismatches: list[str] = Field(
        default_factory=list,
        description="Paths where the runtime type does not match the expected schema type.",
    )
    unexpected_fields: list[str] = Field(
        default_factory=list,
        description="Paths present in the response but not allowed by the schema (strict check).",
    )
    value_issues: list[str] = Field(
        default_factory=list,
        description="Obvious semantic or constraint violations (enums, formats, ranges).",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional short summary from the model.",
    )
