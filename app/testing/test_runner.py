"""
Test execution engine: HTTP call → capture response → existing hybrid validation.

Reuses ``swagger_parser`` + ``run_hybrid_validation_for_request`` (rules + optional LLM + cache).
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import settings
from app.logging_config import get_logger
from app.models.schemas import ValidationResult, ValidationSource
from app.models.testing_schemas import APITestCase, TestExecutionReport
from app.services.hybrid_validator import run_hybrid_validation_for_request
from app.testing import api_client
from app.utils.swagger_parser import OpenAPIParseError, get_response_json_schema

logger = get_logger(__name__)

_PREVIEW_LEN = 2000


def _resolve_spec_path(filename: str) -> Path:
    """Locate ``filename`` under the primary specs dir or configured fallbacks."""
    roots: list[Path] = [Path(settings.swagger_specs_directory).resolve()]
    for fd in settings.swagger_specs_fallback_list():
        roots.append(Path(fd).resolve())
    for root in roots:
        candidate = (root / filename).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"OpenAPI spec file not found: {filename!r} (searched: {roots})")


def load_openapi_file(filename: str) -> dict[str, Any]:
    path = _resolve_spec_path(filename)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("OpenAPI file must contain a JSON object")
    return data


def resolve_request_url(tc: APITestCase) -> str:
    """Absolute URL as-is; relative URL joined with environment base from settings."""
    u = tc.url.strip()
    if u.startswith("http://") or u.startswith("https://"):
        return u
    bases = settings.test_env_base_urls()
    env = (tc.environment or "").strip().lower()
    base = bases.get(env) if env else None
    if base is None:
        base = bases.get("default")
    if not base:
        raise ValueError(
            "Relative test url requires TEST_ENV_BASE_URLS_JSON mapping "
            "(e.g. {\"dev\":\"http://localhost:8080\"}) and matching "
            "`environment` on the test case (or key `default`)."
        )
    if not u.startswith("/"):
        u = "/" + u
    return f"{base}{u}"


def _infer_openapi_path(url: str) -> str:
    path = urlparse(url).path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return path if path else "/"


def _validation_failed(v: ValidationResult) -> bool:
    return bool(
        v.missing_fields or v.type_mismatches or v.unexpected_fields or v.value_issues
    )


def _preview_body(text: str | None) -> str | None:
    if text is None:
        return None
    if len(text) <= _PREVIEW_LEN:
        return text
    return text[:_PREVIEW_LEN] + "…"


async def execute_api_test_case(tc: APITestCase) -> TestExecutionReport:
    """
    Run one test: resolve URL, execute HTTP, validate body against OpenAPI operation schema.
    """
    report_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()

    try:
        final_url = resolve_request_url(tc)
    except ValueError as e:
        logger.warning("Test %s URL resolution failed: %s", tc.name, e)
        return TestExecutionReport(
            id=report_id,
            test_name=tc.name,
            status="FAIL",
            validation=None,
            response_time_ms=0.0,
            timestamp=ts,
            http_status=None,
            error=str(e),
            request_url=tc.url.strip(),
        )

    try:
        openapi_root = load_openapi_file(tc.expected_swagger)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        logger.error("OpenAPI load failed for test %s: %s", tc.name, e)
        return TestExecutionReport(
            id=report_id,
            test_name=tc.name,
            status="FAIL",
            validation=None,
            response_time_ms=0.0,
            timestamp=ts,
            http_status=None,
            error=f"OpenAPI load error: {e}",
            request_url=final_url,
        )

    try:
        capture = await asyncio.to_thread(
            api_client.execute_http,
            tc.method,
            final_url,
            headers=tc.headers or None,
            body=tc.body,
        )
    except RuntimeError as e:
        logger.error("HTTP failed for test %s: %s", tc.name, e)
        return TestExecutionReport(
            id=report_id,
            test_name=tc.name,
            status="FAIL",
            validation=None,
            response_time_ms=0.0,
            timestamp=ts,
            http_status=None,
            error=str(e),
            request_url=final_url,
        )

    openapi_path = tc.openapi_path or _infer_openapi_path(final_url)
    op_method = tc.openapi_method or tc.method.lower()
    status_key = tc.openapi_status_code or str(capture.status_code)

    http_fail_reason: str | None = None
    if tc.expected_http_status is not None and capture.status_code != tc.expected_http_status:
        http_fail_reason = (
            f"Expected HTTP {tc.expected_http_status}, got {capture.status_code}"
        )

    response_body: Any = capture.json_body
    if response_body is None and capture.text:
        # Body present but not JSON (or wrong content-type)
        response_body = capture.text

    validation: ValidationResult | None = None
    if http_fail_reason:
        validation = ValidationResult(
            missing_fields=[],
            type_mismatches=[],
            unexpected_fields=[],
            value_issues=[http_fail_reason],
            confidence_score=1.0,
            validation_source=ValidationSource.RULE_BASED,
            notes=None,
        )
    else:
        try:
            schema = get_response_json_schema(
                openapi_root,
                path=openapi_path,
                method=op_method,
                status_code=status_key,
            )
        except OpenAPIParseError as e:
            logger.info("OpenAPI parse for test %s: %s", tc.name, e)
            validation = ValidationResult(
                missing_fields=[],
                type_mismatches=[],
                unexpected_fields=[],
                value_issues=[f"OpenAPI resolution error: {e}"],
                confidence_score=1.0,
                validation_source=ValidationSource.RULE_BASED,
                notes=None,
            )
        else:
            logger.info(
                "Running hybrid validation for test %s | %s %s [%s]",
                tc.name,
                op_method.upper(),
                openapi_path,
                status_key,
            )
            validation = await run_hybrid_validation_for_request(
                schema,
                response_body,
                path=openapi_path,
                method=op_method,
                status_code=status_key,
                include_schema_in_prompt=tc.include_schema_in_prompt,
                use_llm_semantic=tc.enable_ai_validation,
                skip_llm_on_structural_failure=tc.skip_llm_on_structural_failure,
            )
            logger.info(
                "Test %s validation | source=%s | fail=%s",
                tc.name,
                validation.validation_source,
                _validation_failed(validation),
            )

    assert validation is not None
    failed = _validation_failed(validation)
    status: str = "FAIL" if failed else "PASS"

    return TestExecutionReport(
        id=report_id,
        test_name=tc.name,
        status=status,
        validation=validation,
        response_time_ms=round(capture.elapsed_ms, 2),
        timestamp=ts,
        http_status=capture.status_code,
        error=http_fail_reason,
        request_url=final_url,
        response_body_preview=_preview_body(capture.text) if capture.text else None,
    )


async def execute_test_batch(
    tests: list[APITestCase],
    *,
    parallel: bool,
) -> list[TestExecutionReport]:
    """Run many tests, optionally in parallel with a concurrency cap."""
    if not parallel:
        return [await execute_api_test_case(t) for t in tests]

    sem = asyncio.Semaphore(max(1, settings.test_run_parallel_max))

    async def _one(t: APITestCase) -> TestExecutionReport:
        async with sem:
            return await execute_api_test_case(t)

    return await asyncio.gather(*(_one(t) for t in tests))
