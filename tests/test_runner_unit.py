"""Unit tests for the API test runner (HTTP mocked via asyncio.to_thread)."""
from __future__ import annotations

import pytest

from app.models.testing_schemas import APITestCase
from app.testing.api_client import HTTPResponseCapture
from app.testing.test_runner import execute_api_test_case


@pytest.mark.asyncio
async def test_execute_pass_with_mocked_http(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = HTTPResponseCapture(
        status_code=200,
        headers={"Content-Type": "application/json"},
        elapsed_ms=10.0,
        json_body={"slideshow": {"author": "Yours Truly"}},
        text='{"slideshow":{}}',
        url="https://httpbin.org/json",
        ok=True,
    )

    async def fake_to_thread(fn, *args, **kwargs):  # noqa: ANN001
        return cap

    monkeypatch.setattr("app.testing.test_runner.asyncio.to_thread", fake_to_thread)

    tc = APITestCase(
        name="Mock httpbin",
        method="GET",
        url="https://httpbin.org/json",
        expected_swagger="httpbin_get_json.json",
        enable_ai_validation=False,
        openapi_path="/json",
    )
    report = await execute_api_test_case(tc)
    assert report.status == "PASS"
    assert report.http_status == 200
    assert report.validation is not None
    assert not report.validation.missing_fields


@pytest.mark.asyncio
async def test_execute_fail_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = HTTPResponseCapture(
        status_code=200,
        headers={"Content-Type": "application/json"},
        elapsed_ms=5.0,
        json_body={"id": "not-int", "name": "x", "status": "available", "extra": 1},
        text="{}",
        url="https://api.example/pets/1",
        ok=True,
    )

    async def fake_to_thread(fn, *args, **kwargs):  # noqa: ANN001
        return cap

    monkeypatch.setattr("app.testing.test_runner.asyncio.to_thread", fake_to_thread)

    tc = APITestCase(
        name="Bad pet body",
        method="GET",
        url="https://api.example/pets/1",
        expected_swagger="openapi_pet.json",
        enable_ai_validation=False,
        openapi_path="/pets/1",
    )
    report = await execute_api_test_case(tc)
    assert report.status == "FAIL"
    assert report.validation is not None
    assert (
        report.validation.type_mismatches
        or report.validation.unexpected_fields
        or report.validation.value_issues
    )


@pytest.mark.asyncio
async def test_relative_url_without_env_fails() -> None:
    tc = APITestCase(
        name="No base URL",
        method="GET",
        url="/pets/1",
        expected_swagger="openapi_pet.json",
        enable_ai_validation=False,
        openapi_path="/pets/1",
    )
    report = await execute_api_test_case(tc)
    assert report.status == "FAIL"
    assert report.validation is None
    assert report.http_status is None
    assert report.error and "TEST_ENV_BASE_URLS_JSON" in report.error
