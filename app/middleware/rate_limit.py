"""
Rate limiting via ``slowapi`` (per-IP, configurable requests per minute).
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{max(1, settings.rate_limit_per_minute)}/minute"],
)
