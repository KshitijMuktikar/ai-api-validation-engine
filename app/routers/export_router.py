"""
Export validation results as JSON or CSV (bonus endpoint).
"""
from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.core.exceptions import OpenAPIResolutionError
from app.logging_config import get_logger
from app.models.schemas import ValidationExportRequest
from app.services.hybrid_validator import run_hybrid_validation_for_request
from app.services.openapi_loader import load_openapi_dict
from app.utils.swagger_parser import OpenAPIParseError, get_response_json_schema

router = APIRouter(tags=["export"])
logger = get_logger(__name__)


def _result_to_csv_row(r: dict) -> dict[str, str]:
    return {
        "missing_fields": ";".join(r.get("missing_fields") or []),
        "type_mismatches": ";".join(r.get("type_mismatches") or []),
        "unexpected_fields": ";".join(r.get("unexpected_fields") or []),
        "value_issues": ";".join(r.get("value_issues") or []),
        "confidence_score": str(r.get("confidence_score", "")),
        "validation_source": str(r.get("validation_source", "")),
        "notes": (r.get("notes") or "") or "",
        "cached": str(r.get("cached", False)),
    }


@router.post("/validate/export")
async def validate_export(request: Request, body: ValidationExportRequest) -> Response:
    """
    Run the same validation as ``POST /validate`` and download the result as **json** or **csv**.
    """
    v = body.validation_request
    logger.info("POST /validate/export | format=%s | %s %s", body.format, v.method.upper(), v.path)

    spec = await load_openapi_dict(v)
    try:
        schema = get_response_json_schema(
            spec,
            path=v.path,
            method=v.method,
            status_code=v.status_code,
        )
    except OpenAPIParseError as e:
        raise OpenAPIResolutionError(str(e)) from e

    result = await run_hybrid_validation_for_request(
        schema,
        v.response_body,
        path=v.path,
        method=v.method,
        status_code=v.status_code,
        include_schema_in_prompt=v.include_schema_in_prompt,
        use_llm_semantic=v.use_llm_semantic,
    )

    payload = result.model_dump(mode="json")

    if body.format == "csv":
        buf = io.StringIO()
        row = _result_to_csv_row(payload)
        writer = csv.DictWriter(buf, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)
        return Response(
            content=buf.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="validation_result.csv"',
            },
        )

    return Response(
        content=json.dumps(payload, indent=2, ensure_ascii=False),
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="validation_result.json"',
        },
    )
