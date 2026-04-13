"""Health and readiness endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness/readiness for load balancers and orchestrators."""
    return {
        "status": "ok",
        "service": "ai-api-validation-engine",
        "version": __version__,
        "llm_configured": bool(settings.openai_api_key),
    }
