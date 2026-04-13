"""
Application configuration from environment variables.

Secrets (e.g. OpenAI API key) must come from the environment or `.env` — never hard-code.
"""
from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the validation engine."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: int = 60
    log_level: str = "INFO"
    log_file: str = "logs/app.log"

    # Networking / CORS — restrict in production
    cors_origins: str = Field(
        default="*",
        description="Comma-separated origins, or * for all.",
    )

    # Rate limiting (per minute, per client IP)
    rate_limit_per_minute: int = 60

    # Result cache (in-process TTL)
    validation_cache_ttl_seconds: int = 300
    validation_cache_max_entries: int = 512

    # Batch API safety
    batch_max_items: int = 20

    # --- HTTP API test client (requests) ---
    http_client_timeout_seconds: float = 30.0
    http_client_max_retries: int = 3
    http_client_retry_backoff_factor: float = 0.5
    # Directory containing OpenAPI JSON files referenced by test cases (``expected_swagger``)
    swagger_specs_directory: str = "specs"
    # Fallback search path if file not in swagger_specs_directory
    swagger_specs_fallback_directories: str = "samples"
    # JSON object: {"dev":"http://localhost:8080","qa":"https://qa.example.com"}
    test_env_base_urls_json: str = "{}"
    # In-memory test run history (GET /test-history)
    test_history_max_entries: int = 500
    # POST /run-tests concurrency cap
    test_run_parallel_max: int = 5
    test_run_batch_max_items: int = 50

    @field_validator("cors_origins", mode="before")
    @classmethod
    def strip_cors(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ORIGINS into a list for CORSMiddleware."""
        if self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def test_env_base_urls(self) -> dict[str, str]:
        """Environment name (lowercase) -> base URL for relative test ``url`` values."""
        import json

        try:
            raw = json.loads(self.test_env_base_urls_json or "{}")
        except json.JSONDecodeError:
            return {}
        if not isinstance(raw, dict):
            return {}
        return {str(k).strip().lower(): str(v).rstrip("/") for k, v in raw.items()}

    def swagger_specs_fallback_list(self) -> list[str]:
        return [s.strip() for s in self.swagger_specs_fallback_directories.split(",") if s.strip()]


settings = Settings()
