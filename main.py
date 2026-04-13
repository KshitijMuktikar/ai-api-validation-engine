"""
Application entrypoint for ``uvicorn main:app`` and legacy imports.

The implementation lives under ``app/``.
"""
from app.main import app

__all__ = ["app"]
