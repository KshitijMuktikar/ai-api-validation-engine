"""Load OpenAPI documents from inline JSON or remote URL (async)."""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.exceptions import UpstreamFetchError
from app.logging_config import get_logger
from app.models.schemas import ValidateRequest

logger = get_logger(__name__)


async def load_openapi_dict(req: ValidateRequest) -> dict[str, Any]:
    """
    Return OpenAPI root document as a dict.

    ``ValidateRequest`` is already validated by Pydantic (mutually exclusive spec vs URL).
    """
    if req.openapi_spec is not None:
        return req.openapi_spec

    assert req.openapi_spec_url is not None
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get(req.openapi_spec_url)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        logger.warning("Failed to fetch OpenAPI URL: %s", e)
        raise UpstreamFetchError(
            "Could not fetch openapi_spec_url.",
            details=str(e),
        ) from e
    except json.JSONDecodeError as e:
        raise UpstreamFetchError(
            "URL did not return valid JSON.",
            details=str(e),
        ) from e

    if not isinstance(data, dict):
        raise UpstreamFetchError(
            "OpenAPI document must be a JSON object.",
            details=f"got {type(data).__name__}",
        )
    return data
