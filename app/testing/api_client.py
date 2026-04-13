"""
Synchronous HTTP client for API test execution using ``requests`` + urllib3 retries.

Used from async code via ``asyncio.to_thread`` so the FastAPI event loop stays responsive.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class HTTPResponseCapture:
    """Normalized HTTP response for the test runner and validators."""

    status_code: int
    headers: dict[str, str]
    elapsed_ms: float
    json_body: Any
    text: str
    url: str
    ok: bool


def _build_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=settings.http_client_max_retries,
        connect=settings.http_client_max_retries,
        read=settings.http_client_max_retries,
        backoff_factor=settings.http_client_retry_backoff_factor,
        status_forcelist=(502, 503, 504),
        allowed_methods=frozenset(
            ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
        ),
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _log_request(method: str, url: str, headers: Optional[Mapping[str, str]]) -> None:
    safe_headers = dict(headers or {})
    for k in list(safe_headers.keys()):
        if k.lower() == "authorization":
            safe_headers[k] = "***"
    logger.info("HTTP %s %s | headers=%s", method, url, safe_headers)


def _request(
    method: str,
    url: str,
    *,
    headers: Optional[Mapping[str, str]] = None,
    json_body: Any = None,
    data: Any = None,
) -> HTTPResponseCapture:
    session = _build_session()
    _log_request(method, url, headers)
    t0 = time.perf_counter()
    try:
        try:
            resp = session.request(
                method,
                url,
                headers=dict(headers) if headers else None,
                json=json_body if data is None else None,
                data=data,
                timeout=settings.http_client_timeout_seconds,
            )
        except requests.RequestException as e:
            logger.exception("HTTP request failed: %s %s", method, url)
            raise RuntimeError(f"HTTP request failed: {e}") from e

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        text = resp.text or ""
        parsed: Any = None
        try:
            if text and "application/json" in resp.headers.get("Content-Type", "").lower():
                parsed = resp.json()
        except ValueError:
            parsed = None

        logger.info(
            "HTTP %s %s -> %s in %.1fms | body_len=%d",
            method,
            url,
            resp.status_code,
            elapsed_ms,
            len(text),
        )

        return HTTPResponseCapture(
            status_code=resp.status_code,
            headers={k: v for k, v in resp.headers.items()},
            elapsed_ms=elapsed_ms,
            json_body=parsed,
            text=text,
            url=str(resp.url),
            ok=resp.ok,
        )
    finally:
        session.close()


def send_get(url: str, headers: Optional[Mapping[str, str]] = None) -> HTTPResponseCapture:
    return _request("GET", url, headers=headers)


def send_post(
    url: str,
    body: Any = None,
    headers: Optional[Mapping[str, str]] = None,
) -> HTTPResponseCapture:
    """
    POST with JSON body when ``body`` is a dict or list; otherwise send as raw ``data`` string/bytes.
    """
    if body is None:
        return _request("POST", url, headers=headers)
    if isinstance(body, (dict, list)):
        return _request("POST", url, headers=headers, json_body=body)
    return _request("POST", url, headers=headers, data=body)


def send_put(
    url: str,
    body: Any = None,
    headers: Optional[Mapping[str, str]] = None,
) -> HTTPResponseCapture:
    if body is None:
        return _request("PUT", url, headers=headers)
    if isinstance(body, (dict, list)):
        return _request("PUT", url, headers=headers, json_body=body)
    return _request("PUT", url, headers=headers, data=body)


def send_delete(url: str, headers: Optional[Mapping[str, str]] = None) -> HTTPResponseCapture:
    return _request("DELETE", url, headers=headers)


def execute_http(
    method: str,
    url: str,
    *,
    headers: Optional[Mapping[str, str]] = None,
    body: Any = None,
) -> HTTPResponseCapture:
    """
    Dispatch by verb for the test runner; supports GET/POST/PUT/DELETE/PATCH/HEAD/OPTIONS.
    """
    m = method.strip().upper()
    if m == "GET":
        return send_get(url, headers)
    if m == "POST":
        return send_post(url, body, headers)
    if m == "PUT":
        return send_put(url, body, headers)
    if m == "DELETE":
        return send_delete(url, headers)
    if body is None:
        return _request(m, url, headers=headers)
    if isinstance(body, (dict, list)):
        return _request(m, url, headers=headers, json_body=body)
    return _request(m, url, headers=headers, data=body)
