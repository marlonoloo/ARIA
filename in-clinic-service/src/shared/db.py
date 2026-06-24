"""Aurora PostgreSQL access via the RDS Data API.

Why the Data API instead of psycopg2?
  - No VPC required for the Lambda, so it can also reach Bedrock over the public
    AWS API surface without NAT gateways or VPC endpoints.
  - No connection pool to manage against an Aurora cluster that scales to zero.
  - Credentials come from Secrets Manager (the cluster's managed secret), so no
    passwords live in env vars.

Trade-off (documented for the trade-off doc): the Data API adds per-call latency
and has payload limits. Acceptable for a PoC; revisit for high-throughput prod.
"""
from __future__ import annotations

import json
from typing import Any

import boto3

from shared.config import config
from shared.logging_utils import get_logger

logger = get_logger(__name__)

_client = None


def _data_client():
    global _client
    if _client is None:
        _client = boto3.client("rds-data", region_name=config.region)
    return _client


def _to_param(name: str, value: Any) -> dict:
    """Convert a Python value into an RDS Data API parameter."""
    if value is None:
        return {"name": name, "value": {"isNull": True}}
    if isinstance(value, bool):
        return {"name": name, "value": {"booleanValue": value}}
    if isinstance(value, int):
        return {"name": name, "value": {"longValue": value}}
    if isinstance(value, float):
        return {"name": name, "value": {"doubleValue": value}}
    # Everything else (str, list, dict) is sent as a string. Callers should
    # json.dumps() dicts/lists before passing them in if a JSON/JSONB column
    # is the target.
    return {"name": name, "value": {"stringValue": str(value)}}


def query(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Run a SELECT and return rows as a list of dicts.

    Uses formatRecordsAs=JSON so the Data API does the type marshalling for us.
    """
    parameters = [_to_param(k, v) for k, v in (params or {}).items()]
    response = _data_client().execute_statement(
        resourceArn=config.db_cluster_arn,
        secretArn=config.db_secret_arn,
        database=config.db_name,
        sql=sql,
        parameters=parameters,
        formatRecordsAs="JSON",
    )
    formatted = response.get("formattedRecords")
    if not formatted:
        return []
    return json.loads(formatted)


def query_one(sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run an INSERT/UPDATE/DELETE.

    Append `RETURNING ...` to the SQL and read the result via the returned
    `formattedRecords` if you need generated values back.
    """
    parameters = [_to_param(k, v) for k, v in (params or {}).items()]
    response = _data_client().execute_statement(
        resourceArn=config.db_cluster_arn,
        secretArn=config.db_secret_arn,
        database=config.db_name,
        sql=sql,
        parameters=parameters,
        formatRecordsAs="JSON",
    )
    rows: list[dict[str, Any]] = []
    if response.get("formattedRecords"):
        rows = json.loads(response["formattedRecords"])
    return {
        "rows": rows,
        "rows_updated": response.get("numberOfRecordsUpdated", 0),
    }
