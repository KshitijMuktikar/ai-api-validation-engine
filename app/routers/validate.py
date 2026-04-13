"""Core validation endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.exceptions import OpenAPIResolutionError
from app.logging_config import get_logger
from app.models.schemas import ValidationResult, ValidateRequest
from app.services.hybrid_validator import run_hybrid_validation_for_request
from app.services.openapi_loader import load_openapi_dict
from app.utils.swagger_parser import OpenAPIParseError, get_response_json_schema, summarize_schema

router = APIRouter(tags=["validate"])
logger = get_logger(__name__)


@router.post("/validate", response_model=ValidationResult)
async def validate_endpoint(request: Request, body: ValidateRequest) -> ValidationResult:
    """
    Validate **response_body** against the resolved JSON Schema for the given operation and status.

    Processing order: **Pydantic** request validation → **rule-based** JSON Schema validation →
    optional **LLM** semantic pass (when ``use_llm_semantic`` is true and an API key is set).
    """
    logger.info(
        "POST /validate | %s %s [%s]",
        body.method.upper(),
        body.path,
        body.status_code,
    )

    spec = await load_openapi_dict(body)
    try:
        schema = get_response_json_schema(
            spec,
            path=body.path,
            method=body.method,
            status_code=body.status_code,
        )
    except OpenAPIParseError as e:
        logger.info("OpenAPI parse error: %s", e)
        raise OpenAPIResolutionError(str(e)) from e

    logger.debug("Schema preview: %s", summarize_schema(schema)[:500])

    return await run_hybrid_validation_for_request(
        schema,
        body.response_body,
        path=body.path,
        method=body.method,
        status_code=body.status_code,
        include_schema_in_prompt=body.include_schema_in_prompt,
        use_llm_semantic=body.use_llm_semantic,
    )
