"""
OpenAPI (Swagger) 3.x parser: load specs, resolve $ref, extract response JSON Schema.

Supports OpenAPI 3.0.x/3.1.x. For Swagger 2.0, convert externally or extend this module.
"""
from __future__ import annotations

import copy
from typing import Any, Optional

from logging_config import get_logger

logger = get_logger(__name__)


class OpenAPIParseError(Exception):
    """Raised when the document is invalid or the operation cannot be found."""


def _deref(
    root: dict[str, Any],
    node: Any,
    seen: Optional[set[str]] = None,
) -> Any:
    """
    Resolve internal JSON Pointers (#/...) in-place style without mutating original keys
    beyond returning new structures for resolved refs.
    """
    if seen is None:
        seen = set()

    if not isinstance(node, dict):
        return node

    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/"):
        if ref in seen:
            raise OpenAPIParseError(f"Circular $ref detected: {ref}")
        seen.add(ref)
        parts = ref.lstrip("#/").split("/")
        target: Any = root
        for p in parts:
            p = p.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or p not in target:
                raise OpenAPIParseError(f"Cannot resolve $ref: {ref}")
            target = target[p]
        resolved = _deref(root, copy.deepcopy(target), seen)
        seen.discard(ref)
        return resolved

    out: dict[str, Any] = {}
    for k, v in node.items():
        if k == "$ref":
            continue
        if isinstance(v, dict):
            out[k] = _deref(root, v, seen)
        elif isinstance(v, list):
            out[k] = [_deref(root, i, seen) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    return out


def normalize_path(path: str) -> str:
    """Ensure leading slash and no trailing slash (except root)."""
    p = path.strip()
    if not p.startswith("/"):
        p = "/" + p
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/")
    return p


def _find_path_item(paths: dict[str, Any], path: str) -> tuple[str, dict[str, Any]]:
    """
    Match request path to OpenAPI paths object; supports literal match first,
    then template match (e.g. /pets/{petId}).
    """
    norm = normalize_path(path)
    if norm in paths:
        return norm, paths[norm]

    # Template matching: /pets/{petId} matches /pets/123
    for spec_path, item in paths.items():
        if not isinstance(item, dict):
            continue
        sp = normalize_path(spec_path)
        req_segs = norm.strip("/").split("/")
        spec_segs = sp.strip("/").split("/")
        if len(req_segs) != len(spec_segs):
            continue
        ok = True
        for a, b in zip(req_segs, spec_segs):
            if b.startswith("{") and b.endswith("}"):
                continue
            if a != b:
                ok = False
                break
        if ok:
            return sp, item

    raise OpenAPIParseError(f"No path match for '{path}' in OpenAPI paths.")


def get_response_json_schema(
    openapi_root: dict[str, Any],
    path: str,
    method: str,
    status_code: str,
) -> dict[str, Any]:
    """
    Extract the JSON Schema for the response body (application/json preferred).

    Returns a resolved schema dict suitable for LLM and documentation.
    """
    if "openapi" not in openapi_root and "swagger" in openapi_root:
        raise OpenAPIParseError(
            "Swagger 2.0 detected. Convert to OpenAPI 3 or use an OAS3 spec. "
            "This engine targets OpenAPI 3.x."
        )

    paths = openapi_root.get("paths")
    if not isinstance(paths, dict):
        raise OpenAPIParseError("OpenAPI document has no 'paths' object.")

    _, path_item = _find_path_item(paths, path)
    op_key = method.lower()
    if op_key not in path_item:
        raise OpenAPIParseError(
            f"Method '{method}' not defined for path. Available: {[k for k in path_item if k in ('get','put','post','delete','patch','options','head','trace')]}"
        )

    operation = path_item[op_key]
    if not isinstance(operation, dict):
        raise OpenAPIParseError("Invalid operation object.")

    responses = operation.get("responses")
    if not isinstance(responses, dict):
        raise OpenAPIParseError("Operation has no 'responses'.")

    code_key = str(status_code)
    resp = responses.get(code_key)
    if resp is None and "default" in responses:
        resp = responses["default"]
    if not isinstance(resp, dict):
        raise OpenAPIParseError(
            f"Response for status '{status_code}' not found. Keys: {list(responses.keys())}"
        )

    content = resp.get("content")
    if not isinstance(content, dict):
        # OAS might omit body (204); return empty schema meaning "no body expected"
        logger.info("No response content for %s %s %s — empty body schema.", method, path, code_key)
        return {"type": "null", "description": "No response body defined for this status."}

    # Prefer application/json; fall back to first JSON-like
    media = None
    for mt in ("application/json", "application/problem+json", "application/*+json"):
        if mt in content:
            media = content[mt]
            break
    if media is None:
        for key, val in content.items():
            if "json" in key.lower() and isinstance(val, dict):
                media = val
                break
    if not isinstance(media, dict):
        raise OpenAPIParseError(
            f"No JSON-compatible media type in response content. Types: {list(content.keys())}"
        )

    schema = media.get("schema")
    if schema is None:
        return {"type": "object", "description": "Response has content but no schema."}

    resolved = _deref(openapi_root, schema)
    if not isinstance(resolved, dict):
        return {"type": "string", "description": "Non-object schema root."}
    return resolved


def summarize_schema(schema: dict[str, Any], max_depth: int = 6) -> str:
    """Produce a compact text summary for logs (not for LLM — full schema is passed separately)."""
    import json

    try:
        s = json.dumps(schema, indent=2)
        if len(s) > 4000:
            return s[:4000] + "\n... (truncated)"
        return s
    except (TypeError, ValueError):
        return str(schema)
