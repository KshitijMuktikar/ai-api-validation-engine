"""
Shared pytest fixtures.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def pet_openapi() -> dict:
    with open(SAMPLES / "openapi_pet.json", encoding="utf-8") as f:
        return json.load(f)
