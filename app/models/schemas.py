"""
Pydantic models for API contracts.

All request bodies are validated before business logic runs. Malformed JSON is rejected
by FastAPI/Starlette before handlers execute.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class ValidationSource(str, Enum):
    """Which validation path produced (or dominated) the result."""

    RULE_BASED = "rule_based"
    LLM = "llm"
    HYBRID = "hybrid"


class ErrorResponse(BaseModel):
    """Standard error envelope for clients and proxies."""

    error: str = Field(..., description="Human-readable error message.")
    details: Optional[str] = Field(default=None, description="Optional technical detail.")


class ValidateRequest(BaseModel):
    """Body for POST /validate."""

    openapi_spec: Optional[dict[str, Any]] = Field(
        default=None,
        description="Full OpenAPI 3.x specification as a JSON object.",
    )
    openapi_spec_url: Optional[str] = Field(
        default=None,
        description="HTTPS URL returning OpenAPI JSON.",
    )
    path: str = Field(..., min_length=1, max_length=2048, description="Path as in the spec.")
    method: str = Field(..., min_length=1, max_length=16, description="HTTP method, e.g. get, post.")
    status_code: str = Field(
        default="200",
        min_length=1,
        max_length=16,
        description="Response status key as in OpenAPI, e.g. 200 or default.",
    )
    response_body: Any = Field(
        ...,
        description="JSON value to validate (object, array, string, number, boolean, or null).",
    )
    include_schema_in_prompt: bool = Field(
        default=True,
        description="Include resolved JSON Schema in the LLM context (recommended).",
    )
    use_llm_semantic: bool = Field(
        default=True,
        description="If true, run secondary LLM pass for semantic / edge-case issues.",
    )

    @field_validator("method")
    @classmethod
    def method_lower(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("path")
    @classmethod
    def path_non_empty(cls, v: str) -> str:
        p = v.strip()
        if not p:
            raise ValueError("path must not be empty")
        return p

    @field_validator("openapi_spec_url")
    @classmethod
    def url_if_set(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        if not s:
            return None
        if not (s.startswith("http://") or s.startswith("https://")):
            raise ValueError("openapi_spec_url must be an http(s) URL")
        return s

    @model_validator(mode="after")
    def spec_xor_url(self) -> ValidateRequest:
        if self.openapi_spec is not None and self.openapi_spec_url:
            raise ValueError("Provide only one of openapi_spec or openapi_spec_url, not both.")
        if self.openapi_spec is None and not self.openapi_spec_url:
            raise ValueError("Either openapi_spec or openapi_spec_url is required.")
        if self.openapi_spec is not None and not isinstance(self.openapi_spec, dict):
            raise ValueError("openapi_spec must be a JSON object.")
        if self.openapi_spec is not None:
            keys = set(self.openapi_spec.keys())
            if "openapi" not in keys and "swagger" not in keys:
                raise ValueError("openapi_spec must include an 'openapi' or 'swagger' version field.")
        return self


class ValidationResult(BaseModel):
    """Structured validation output (rule-based, LLM, or hybrid)."""

    missing_fields: list[str] = Field(default_factory=list)
    type_mismatches: list[str] = Field(default_factory=list)
    unexpected_fields: list[str] = Field(default_factory=list)
    value_issues: list[str] = Field(default_factory=list)
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Heuristic confidence in the combined assessment (1.0 = fully deterministic rules).",
    )
    validation_source: ValidationSource = Field(
        ...,
        description="rule_based | llm | hybrid",
    )
    notes: Optional[str] = Field(default=None, description="Optional short summary (often from LLM).")
    cached: bool = Field(default=False, description="True if this result was served from cache.")


class BatchValidateRequest(BaseModel):
    """POST /validate/batch — multiple independent validations."""

    items: list[ValidateRequest] = Field(..., min_length=1)

    @field_validator("items")
    @classmethod
    def cap_batch(cls, v: list[ValidateRequest]) -> list[ValidateRequest]:
        # Dynamic max from settings applied in router; keep pydantic reasonable upper bound
        if len(v) > 100:
            raise ValueError("Too many items in batch (max 100 per request body cap).")
        return v


class BatchValidateResponse(BaseModel):
    """Batch results in the same order as ``items``."""

    results: list[ValidationResult]


class ExportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"


class ValidationExportRequest(BaseModel):
    """Run validation and return a downloadable artifact."""

    validation_request: ValidateRequest = Field(
        ...,
        description="Same payload shape as POST /validate.",
    )
    format: Literal["json", "csv"] = Field(default="json")
