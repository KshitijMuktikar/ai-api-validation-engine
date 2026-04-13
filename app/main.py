"""
FastAPI application factory and global middleware / exception wiring.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.status import (
    HTTP_422_UNPROCESSABLE_CONTENT,
    HTTP_429_TOO_MANY_REQUESTS,
    HTTP_500_INTERNAL_SERVER_ERROR,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app import __version__
from app.config import settings
from app.core.exceptions import AppError
from app.logging_config import get_logger, setup_logging
from app.middleware.rate_limit import limiter
from app.models.schemas import ErrorResponse
from app.routers import batch, export_router, health, run_testing, validate

setup_logging()
logger = get_logger(__name__)


def _error_body(message: str, details: str | None = None) -> dict[str, Any]:
    return ErrorResponse(error=message, details=details).model_dump(exclude_none=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Starting AI API Validation Engine v%s | model=%s | log_level=%s | rate_limit=%s/min",
        __version__,
        settings.openai_model,
        settings.log_level,
        settings.rate_limit_per_minute,
    )
    yield
    logger.info("Shutdown complete.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI-Powered API Validation Engine",
        description=(
            "Validate API JSON responses against OpenAPI 3.x with a **hybrid** engine: "
            "deterministic JSON Schema rules plus an optional OpenAI semantic pass."
        ),
        version=__version__,
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        logger.warning("AppError: %s | %s", exc.message, exc.details)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Malformed JSON / invalid Pydantic input
        errs = exc.errors()
        logger.info("Request validation failed: %s", errs)
        detail = "; ".join(f"{e.get('loc')}: {e.get('msg')}" for e in errs[:5])
        return JSONResponse(
            status_code=HTTP_422_UNPROCESSABLE_CONTENT,
            content=_error_body("Invalid request body", details=detail or str(exc)),
        )

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(_request: Request, exc: RateLimitExceeded) -> JSONResponse:
        logger.warning("Rate limit exceeded: %s", exc.detail)
        return JSONResponse(
            status_code=HTTP_429_TOO_MANY_REQUESTS,
            content=_error_body("Too many requests", details="Rate limit exceeded for this client."),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")
        return JSONResponse(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body("Internal server error", details=str(exc) if settings.log_level == "DEBUG" else None),
        )

    app.include_router(health.router)
    app.include_router(validate.router)
    app.include_router(batch.router)
    app.include_router(export_router.router)
    app.include_router(run_testing.router)

    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.is_dir():
        app.mount(
            "/ui",
            StaticFiles(directory=str(static_dir), html=True),
            name="ui",
        )

    return app


app = create_app()
