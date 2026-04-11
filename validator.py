"""
LLM-based comparison of an actual API response against an expected JSON Schema
derived from OpenAPI. Uses OpenAI structured JSON output.
"""
from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from config import settings
from logging_config import get_logger
from schemas import ValidationResult

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Exact prompt template (system + user) for comparing expected vs actual
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert API contract validator. You compare an ACTUAL JSON \
response body against an EXPECTED JSON Schema (OpenAPI 3) and list concrete issues.

Rules:
1. Use JSON Pointer–style paths for field locations (e.g. /user/email, /items/0/id). \
Use "/" for the root when the issue applies to the whole body.
2. missing_fields: required properties or array items mandated by the schema that are absent \
in the actual JSON.
3. type_mismatches: where the JSON type of a value does not match the schema (string vs number, \
object vs array, etc.).
4. unexpected_fields: properties present in the actual JSON that are NOT allowed by the schema \
(additionalProperties: false or not in properties). If the schema allows additional properties, \
do not list extras here unless they clearly violate explicit pattern/structure.
5. value_issues: obvious violations of enum, format (date, email, uuid), min/max, minLength, \
maxLength, or clearly wrong semantics described in the schema description.
6. Be conservative: only report value_issues when the spec or common sense makes the error obvious.
7. Output MUST be a single JSON object with keys: missing_fields, type_mismatches, \
unexpected_fields, value_issues (each an array of strings), and optional notes (string).

Do not include markdown fences. Return raw JSON only."""


def build_user_prompt(
    expected_schema: dict[str, Any],
    actual_response: Any,
    include_schema: bool = True,
) -> str:
    schema_block = (
        json.dumps(expected_schema, indent=2)
        if include_schema
        else "(schema omitted; infer from context is not available — include_schema should be true)"
    )
    actual_block = json.dumps(actual_response, indent=2, default=str)
    return f"""EXPECTED JSON SCHEMA (from OpenAPI response schema, $ref resolved):

{schema_block}

---

ACTUAL API RESPONSE BODY (JSON):

{actual_block}

---

Analyze and return JSON with keys missing_fields, type_mismatches, unexpected_fields, value_issues, notes."""


def validate_with_llm(
    expected_schema: dict[str, Any],
    actual_response: Any,
    *,
    include_schema: bool = True,
) -> ValidationResult:
    """
    Call OpenAI to compare actual response to expected schema.
    Requires OPENAI_API_KEY in settings.
    """
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set. Add it to your environment or .env file.")

    client = OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)

    user_content = build_user_prompt(expected_schema, actual_response, include_schema)

    logger.debug("LLM user prompt length: %s chars", len(user_content))

    # Prefer JSON response format for reliable parsing
    completion = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )

    raw = completion.choices[0].message.content or "{}"
    logger.debug("LLM raw response: %s", raw[:2000])

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("LLM returned invalid JSON: %s", e)
        return ValidationResult(
            value_issues=[f"LLM returned invalid JSON: {e}"],
            notes=raw[:500],
        )

    return ValidationResult(
        missing_fields=list(data.get("missing_fields") or []),
        type_mismatches=list(data.get("type_mismatches") or []),
        unexpected_fields=list(data.get("unexpected_fields") or []),
        value_issues=list(data.get("value_issues") or []),
        notes=data.get("notes"),
    )
