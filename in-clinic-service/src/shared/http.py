"""API Gateway (proxy integration) request/response helpers."""
from __future__ import annotations

import json
from typing import Any

_RESPONSE_HEADERS = {
    "Content-Type": "application/json",
    # NOTE: CORS (Access-Control-Allow-*) is owned by API Gateway, not the
    # Lambda. Returning CORS headers here too would duplicate them and the
    # browser would reject the response. Configure CORS on the HTTP API instead.
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
        "headers": _RESPONSE_HEADERS,
        "body": json.dumps(payload, default=str),
    }


def ok(payload: dict[str, Any]) -> dict[str, Any]:
    return response(200, payload)


def error(status_code: int, message: str) -> dict[str, Any]:
    return response(status_code, {"error": message})


class BadRequest(Exception):
    """Raised for client-side (4xx) input problems."""
