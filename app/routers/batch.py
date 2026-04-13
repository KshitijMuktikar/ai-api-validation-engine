"""Batch validation endpoint (optional / bonus)."""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.config import settings
from app.core.exceptions import AppError
from app.logging_config import get_logger
from app.models.schemas import (
    BatchValidateRequest,
    BatchValidateResponse,
    ValidationResult,
    ValidationSource,
)
from app.services.hybrid_validator import run_hybrid_validation_for_request
from app.services.openapi_loader import load_openapi_dict
from app.utils.swagger_parser import OpenAPIParseError, get_response_json_schema

router = APIRouter(tags=["batch"])
logger = get_logger(__name__)


def _error_result(message: str, details: str | None) -> ValidationResult:
    return ValidationResult(
        missing_fields=[],
        type_mismatches=[],
        unexpected_fields=[],
        value_issues=[message],
        confidence_score=1.0,
        validation_source=ValidationSource.RULE_BASED,
        notes=details,
    )


async def _validate_one(body) -> ValidationResult:
    try:
        spec = await load_openapi_dict(body)
    except AppError as e:
        return _error_result(e.message, e.details)

    try:
        schema = get_response_json_schema(
            spec,
            path=body.path,
            method=body.method,
            status_code=body.status_code,
        )
    except OpenAPIParseError as e:
        return _error_result(f"OpenAPI error: {e}", None)

    return await run_hybrid_validation_for_request(
        schema,
        body.response_body,
        path=body.path,
        method=body.method,
        status_code=body.status_code,
        include_schema_in_prompt=body.include_schema_in_prompt,
        use_llm_semantic=body.use_llm_semantic,
    )


@router.post("/validate/batch", response_model=BatchValidateResponse)
async def validate_batch(request: Request, payload: BatchValidateRequest) -> BatchValidateResponse:
    """
    Run multiple validations in one request (same semantics as ``POST /validate`` per item).

    Maximum items per call is capped by ``BATCH_MAX_ITEMS`` (default 20).
    """
    if len(payload.items) > settings.batch_max_items:
        raise AppError(
            "Batch too large",
            details=f"Maximum {settings.batch_max_items} items allowed.",
            status_code=400,
        )

    logger.info("POST /validate/batch | count=%d", len(payload.items))

    results = [await _validate_one(item) for item in payload.items]
    return BatchValidateResponse(results=results)
