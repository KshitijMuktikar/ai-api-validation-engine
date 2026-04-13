"""
Hybrid pipeline: deterministic JSON Schema rules first, optional async LLM semantic pass.
"""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.core.exceptions import LLMUnavailableError
from app.logging_config import get_logger
from app.models.schemas import ValidationResult, ValidationSource
from app.services.cache_service import ValidationCache, get_validation_cache
from app.services.llm_validator import validate_with_llm_async
from app.services.rule_validator import validate_with_rules

logger = get_logger(__name__)


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _merge_value_issues(rule_vals: list[str], llm_vals: list[str]) -> list[str]:
    return _dedupe_preserve_order(list(rule_vals) + list(llm_vals))


def _confidence(source: ValidationSource, had_llm: bool) -> float:
    if source == ValidationSource.RULE_BASED:
        return 1.0
    if source == ValidationSource.HYBRID:
        return 0.92 if had_llm else 1.0
    return 0.9


async def run_hybrid_validation_for_request(
    schema: dict[str, Any],
    response_body: Any,
    *,
    path: str,
    method: str,
    status_code: str,
    include_schema_in_prompt: bool,
    use_llm_semantic: bool,
    skip_llm_on_structural_failure: bool = False,
) -> ValidationResult:
    """
    Rule-based validation, optional LLM semantic enrichment, with TTL cache.

    If ``skip_llm_on_structural_failure`` is true and the rule engine reports any
    missing fields, type mismatches, or unexpected fields, the LLM pass is skipped
    (cost/latency optimization while keeping deterministic failures).
    """
    cache = get_validation_cache()
    cache_key = ValidationCache.make_key(
        schema,
        response_body,
        path=path,
        method=method,
        status_code=status_code,
        use_llm_semantic=use_llm_semantic,
        include_schema_in_prompt=include_schema_in_prompt,
        skip_llm_on_structural_failure=skip_llm_on_structural_failure,
    )

    if settings.validation_cache_ttl_seconds > 0:
        hit = cache.get(cache_key)
        if hit is not None:
            logger.info("Validation cache hit for %s %s [%s]", method.upper(), path, status_code)
            return hit

    rule_result = validate_with_rules(schema, response_body)
    merged = rule_result.model_copy(deep=True)
    final_source = ValidationSource.RULE_BASED
    had_llm = False
    notes_out: str | None = None

    structural_fail = bool(
        rule_result.missing_fields
        or rule_result.type_mismatches
        or rule_result.unexpected_fields
    )
    effective_llm = use_llm_semantic and not (
        skip_llm_on_structural_failure and structural_fail
    )
    if skip_llm_on_structural_failure and structural_fail and use_llm_semantic:
        logger.info(
            "Skipping LLM: structural rule failures present (missing/type/unexpected)."
        )
        notes_out = "LLM pass skipped: structural rule violations already detected."

    if effective_llm:
        if not settings.openai_api_key:
            logger.info("LLM semantic requested but OPENAI_API_KEY missing; rule-based only.")
            notes_out = "LLM semantic pass skipped: API key not configured."
        else:
            try:
                llm_partial = await validate_with_llm_async(
                    schema,
                    response_body,
                    include_schema=include_schema_in_prompt,
                    rule_findings=rule_result,
                )
                had_llm = True
                merged.value_issues = _merge_value_issues(
                    rule_result.value_issues,
                    llm_partial.value_issues,
                )
                final_source = ValidationSource.HYBRID
                notes_out = llm_partial.notes
            except LLMUnavailableError as e:
                logger.warning("LLM unavailable: %s", e.message)
                notes_out = e.message if not e.details else f"{e.message} ({e.details})"
            except Exception as e:
                logger.exception("LLM semantic pass failed")
                notes_out = f"LLM semantic pass failed: {e}"

    merged.validation_source = final_source
    merged.confidence_score = _confidence(final_source, had_llm)
    merged.notes = notes_out
    merged.cached = False

    if settings.validation_cache_ttl_seconds > 0:
        cache.set(cache_key, merged)

    logger.info(
        "Validation done | source=%s | missing=%d type=%d extra=%d value=%d",
        final_source.value,
        len(merged.missing_fields),
        len(merged.type_mismatches),
        len(merged.unexpected_fields),
        len(merged.value_issues),
    )

    return merged
