"""Bedrock helpers: Knowledge Base retrieval + Claude via the Converse API.

We deliberately split retrieval from generation (instead of using
retrieve_and_generate) so we can:
  - inject patient context into the prompt alongside retrieved protocols, and
  - force a strict JSON output shape that maps onto the clinical_briefings table.

Retrieval note: we call `retrieve` with ONLY knowledgeBaseId + retrievalQuery
and no retrievalConfiguration. The KB is a fully-managed type, which rejects
`vectorSearchConfiguration`, and the Lambda runtime's bundled botocore does not
yet model `managedSearchConfiguration`. Omitting the config lets the service
apply its defaults (max 5 results) — this is exactly what the working CLI test
did. To tune retrieval later, upgrade botocore via a Lambda layer and add the
appropriate configuration here.
"""
from __future__ import annotations

import json
from typing import Any

import boto3

from shared.config import config
from shared.logging_utils import get_logger

logger = get_logger(__name__)

_agent_client = None
_runtime_client = None


def _agent():
    global _agent_client
    if _agent_client is None:
        _agent_client = boto3.client("bedrock-agent-runtime", region_name=config.region)
    return _agent_client


def _runtime():
    global _runtime_client
    if _runtime_client is None:
        _runtime_client = boto3.client("bedrock-runtime", region_name=config.region)
    return _runtime_client


def retrieve_protocols(query_text: str) -> list[dict[str, Any]]:
    """Retrieve the most relevant clinical-protocol passages from the KB.

    Returns a list of {"text", "score", "source"} dicts, highest score first.
    """
    response = _agent().retrieve(
        knowledgeBaseId=config.knowledge_base_id,
        retrievalQuery={"text": query_text},
    )

    results = []
    for item in response.get("retrievalResults", []):
        location = item.get("location", {})
        source = (
            location.get("s3Location", {}).get("uri")
            or location.get("type")
            or "unknown"
        )
        results.append(
            {
                "text": item.get("content", {}).get("text", ""),
                "score": item.get("score"),
                "source": source,
            }
        )
    logger.info(
        "kb_retrieve_complete",
        extra={"extra": {"query": query_text[:120], "hits": len(results)}},
    )
    return results


def format_protocol_context(passages: list[dict[str, Any]]) -> str:
    """Render retrieved passages into a citable block for the prompt."""
    if not passages:
        return "No matching clinical protocols were retrieved."
    blocks = []
    for i, p in enumerate(passages, start=1):
        blocks.append(f"[Protocol {i}] (source: {p['source']})\n{p['text']}")
    return "\n\n".join(blocks)


def converse_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """Call Claude via Converse and parse a JSON object from the reply.

    The model is instructed to return only JSON; we still defensively strip
    markdown fences and locate the outermost JSON object before parsing.
    """
    response = _runtime().converse(
        modelId=config.model_id,
        system=[{"text": system_prompt}],
        messages=[{"role": "user", "content": [{"text": user_prompt}]}],
        inferenceConfig={
            "maxTokens": config.max_tokens,
            "temperature": config.temperature,
        },
    )
    text = response["output"]["message"]["content"][0]["text"]
    usage = response.get("usage", {})
    logger.info("bedrock_converse_complete", extra={"extra": {"usage": usage}})
    return _parse_json(text)


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    # Strip ```json ... ``` fences if present.
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.lstrip().lower().startswith("json"):
            cleaned = cleaned.lstrip()[4:]
    # Fall back to slicing the outermost object if there's stray prose.
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error(
            "bedrock_json_parse_failed",
            extra={"extra": {"raw": text[:500]}},
        )
        raise ValueError(f"Model did not return valid JSON: {exc}") from exc
