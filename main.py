"""
FastAPI application: AI-Powered API Validation Engine.

Validates a JSON response body against an OpenAPI 3.x operation response schema using an LLM.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from logging_config import get_logger, setup_logging
from schemas import ValidateRequest, ValidationResult
from swagger_parser import OpenAPIParseError, get_response_json_schema, summarize_schema
from validator import validate_with_llm

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hooks."""
    logger.info(
        "Starting AI API Validation Engine | model=%s | log_level=%s",
        settings.openai_model,
        settings.log_level,
    )
    yield
    logger.info("Shutdown complete.")


app = FastAPI(
    title="AI-Powered API Validation Engine",
    description=(
        "Validate API JSON responses against OpenAPI 3.x schemas using OpenAI. "
        "POST /validate with your spec, path, method, status code, and response body."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _load_openapi(req: ValidateRequest) -> dict[str, Any]:
    """Load OpenAPI document from inline body or URL."""
    if req.openapi_spec is not None and req.openapi_spec_url:
        raise HTTPException(
            status_code=400,
            detail="Provide only one of openapi_spec or openapi_spec_url, not both.",
        )
    if req.openapi_spec is not None:
        return req.openapi_spec
    if req.openapi_spec_url:
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                r = await client.get(req.openapi_spec_url)
                r.raise_for_status()
                return r.json()
        except httpx.HTTPError as e:
            logger.warning("Failed to fetch OpenAPI URL: %s", e)
            raise HTTPException(status_code=502, detail=f"Could not fetch openapi_spec_url: {e}") from e
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"URL did not return JSON: {e}") from e
    raise HTTPException(status_code=400, detail="Either openapi_spec or openapi_spec_url is required.")


@app.get("/health")
async def health():
    """Liveness/readiness for load balancers."""
    return {"status": "ok", "service": "ai-api-validation-engine"}


@app.post("/validate", response_model=ValidationResult)
async def validate_endpoint(body: ValidateRequest) -> ValidationResult:
    """
    Compare **response_body** to the JSON Schema for the given operation and status code.

    - **openapi_spec**: full OpenAPI 3.x JSON object, **or**
    - **openapi_spec_url**: HTTPS URL returning OpenAPI JSON
    """
    spec = await _load_openapi(body)
    try:
        schema = get_response_json_schema(
            spec,
            path=body.path,
            method=body.method,
            status_code=body.status_code,
        )
    except OpenAPIParseError as e:
        logger.info("OpenAPI parse error: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e

    logger.info(
        "Validating %s %s [%s] | schema preview: %s",
        body.method.upper(),
        body.path,
        body.status_code,
        summarize_schema(schema)[:200],
    )

    try:
        result = validate_with_llm(
            schema,
            body.response_body,
            include_schema=body.include_schema_in_prompt,
        )
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.exception("LLM validation failed")
        raise HTTPException(status_code=502, detail=f"Upstream LLM error: {e}") from e

    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
