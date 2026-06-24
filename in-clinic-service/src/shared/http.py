"""API Gateway (proxy integration) request/response helpers."""
from __future__ import annotations

import json
from typing import Any

_CORS_HEADERS = {
    "Content-Type": "application/json",
    # Demo frontend is served from CloudFront/S3; tighten this to the exact
    # origin before anything resembling production.
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
}


def parse_body(event: dict[str, Any]) -> dict[str, Any]:
    """Extract and JSON-parse the body from an API Gateway proxy event."""
    body = event.get("body")
    if body is None:
        return {}
    if isinstance(body, dict):
        return body
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise BadRequest(f"Request body is not valid JSON: {exc}") from exc


def response(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": _CORS_HEADERS,
        "body": json.dumps(payload, default=str),
    }


def ok(payload: dict[str, Any]) -> dict[str, Any]:
    return response(200, payload)


def error(status_code: int, message: str) -> dict[str, Any]:
    return response(status_code, {"error": message})


class BadRequest(Exception):
    """Raised for client-side (4xx) input problems."""
