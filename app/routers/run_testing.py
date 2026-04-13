"""
API test execution endpoints (Rest Assured–style) wired to the hybrid validation engine.
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.config import settings
from app.core.exceptions import AppError
from app.models.testing_schemas import APITestCase, RunTestsBatchRequest, TestExecutionReport
from app.services.test_history import get_test_history_store
from app.testing.test_runner import execute_api_test_case, execute_test_batch

router = APIRouter(tags=["testing"])


@router.post("/run-test", response_model=TestExecutionReport)
async def run_test(request: Request, body: APITestCase) -> TestExecutionReport:
    """
    Execute a single API test: HTTP request → hybrid validation (rules + optional AI).

    Appends the report to in-memory history (``GET /test-history``).
    """
    report = await execute_api_test_case(body)
    get_test_history_store().append(report.model_dump(mode="json"))
    return report


@router.post("/run-tests", response_model=list[TestExecutionReport])
async def run_tests(request: Request, payload: RunTestsBatchRequest) -> list[TestExecutionReport]:
    """
    Run multiple tests. With ``parallel: true``, execution uses asyncio with a bounded
    concurrency limit (``TEST_RUN_PARALLEL_MAX``).
    """
    if len(payload.tests) > settings.test_run_batch_max_items:
        raise AppError(
            "Too many tests in batch",
            details=f"Maximum is {settings.test_run_batch_max_items}.",
            status_code=400,
        )
    reports = await execute_test_batch(payload.tests, parallel=payload.parallel)
    store = get_test_history_store()
    for r in reports:
        store.append(r.model_dump(mode="json"))
    return reports


@router.get("/test-history")
async def test_history(limit: int = Query(50, ge=1, le=200)) -> list[dict]:
    """Recent test reports (newest first), for dashboards or CI inspection."""
    return get_test_history_store().list_recent(limit)
