"""
Pydantic models for API test execution (Rest Assured–style) and reporting.
"""
from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.schemas import ValidationResult


_SAFE_SWAGGER_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


class APITestCase(BaseModel):
    """
    Single executable API test + OpenAPI contract reference.

    ``expected_swagger`` is a file name (e.g. ``openapi_pet.json``) resolved under
    ``swagger_specs_directory`` and optional fallback dirs from settings.
    """

    name: str = Field(..., min_length=1, max_length=256)
    method: str = Field(..., description="GET, POST, PUT, DELETE, ...")
    url: str = Field(..., min_length=1, max_length=4096)
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = Field(default=None, description="JSON-serializable body for POST/PUT/PATCH.")
    expected_swagger: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="OpenAPI JSON file name (not a path with slashes).",
    )
    enable_ai_validation: bool = Field(
        default=True,
        description="If true, allow LLM semantic pass when API key is configured.",
    )
    skip_llm_on_structural_failure: bool = Field(
        default=True,
        description="Skip LLM when rule engine finds missing/type/unexpected field issues.",
    )
    environment: Optional[str] = Field(
        default=None,
        description="Key into TEST_ENV_BASE_URLS_JSON for relative URLs.",
    )
    openapi_path: Optional[str] = Field(
        default=None,
        description="Path in the OpenAPI document; defaults to URL path.",
    )
    openapi_method: Optional[str] = Field(
        default=None,
        description="Operation method for schema lookup; defaults to test method.",
    )
    openapi_status_code: Optional[str] = Field(
        default=None,
        description="OpenAPI response code key; defaults to actual HTTP status.",
    )
    expected_http_status: Optional[int] = Field(
        default=None,
        description="If set, test FAILs when the HTTP status differs.",
    )
    include_schema_in_prompt: bool = Field(default=True)

    @field_validator("method")
    @classmethod
    def method_upper(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("openapi_method")
    @classmethod
    def openapi_method_lower(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v.strip().lower()

    @field_validator("expected_swagger")
    @classmethod
    def swagger_filename_only(cls, v: str) -> str:
        s = v.strip()
        if not _SAFE_SWAGGER_NAME.match(s):
            raise ValueError(
                "expected_swagger must be a simple file name (no path separators or '..')."
            )
        return s


class RunTestsBatchRequest(BaseModel):
    """Batch test execution for POST /run-tests."""

    tests: list[APITestCase] = Field(..., min_length=1)
    parallel: bool = Field(
        default=True,
        description="Run tests concurrently (bounded by TEST_RUN_PARALLEL_MAX).",
    )


class TestExecutionReport(BaseModel):
    """Unified report for UI, CI, and history APIs."""

    id: str = Field(..., description="Unique id for this run.")
    test_name: str
    status: Literal["PASS", "FAIL"]
    validation: Optional[ValidationResult] = None
    response_time_ms: float = Field(..., description="HTTP round-trip time in milliseconds.")
    timestamp: str = Field(..., description="UTC ISO-8601 timestamp.")
    http_status: Optional[int] = None
    error: Optional[str] = Field(default=None, description="Transport / runner error message.")
    request_url: str = Field(..., description="Final URL after environment base resolution.")
    response_body_preview: Optional[str] = Field(
        default=None,
        description="Truncated response body for debugging (not for large payloads in prod logs).",
    )
