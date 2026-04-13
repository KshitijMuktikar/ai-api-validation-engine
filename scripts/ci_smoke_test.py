#!/usr/bin/env python3
"""
CI smoke: run one in-process API test against the public httpbin /json endpoint.

Requires outbound HTTPS. Fails non-zero if the test does not PASS.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Repo root on path when executed as `python scripts/ci_smoke_test.py`
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.models.testing_schemas import APITestCase  # noqa: E402
from app.testing.test_runner import execute_api_test_case  # noqa: E402


async def main() -> int:
    tc = APITestCase(
        name="CI smoke — httpbin GET /json",
        method="GET",
        url="https://httpbin.org/json",
        headers={},
        body=None,
        expected_swagger="httpbin_get_json.json",
        enable_ai_validation=False,
        openapi_path="/json",
        openapi_method="get",
    )
    report = await execute_api_test_case(tc)
    print(json.dumps(report.model_dump(mode="json"), indent=2))
    if report.status != "PASS":
        print("SMOKE FAILED: expected PASS", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
