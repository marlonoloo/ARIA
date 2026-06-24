"""Lambda 1: generateClinicalBriefing.

Trigger: POST /briefing  (doctor selects a patient on the dashboard)

Flow:
  1. Read patient + latest pre-triage session from Aurora.
  2. If the patient was a walk-in (not pre-triaged), return basic info only.
  3. Retrieve relevant clinical protocols from the Bedrock Knowledge Base.
  4. Ask Claude (Converse) for a structured briefing grounded in those protocols.
  5. Persist the briefing to clinical_briefings and return it.

Schema note: primary keys are UUIDs (patient_id, session_id, briefing_id). All
UUID bound parameters are cast with CAST(:x AS uuid) because the Data API sends
parameters as text and Postgres will not implicitly compare uuid = text.
"""
from __future__ import annotations

import json
import uuid

from shared import bedrock, db, enums, prompts
from shared.http import BadRequest, error, ok, parse_body
from shared.logging_utils import get_logger

logger = get_logger("generateClinicalBriefing")


def _load_patient(patient_id: str) -> dict | None:
    return db.query_one(
        """
        SELECT patient_id, full_name, phone_number, preferred_language,
               date_of_birth, gender, literacy_level, intake_method
        FROM patients
        WHERE patient_id = CAST(:pid AS uuid)
        """,
        {"pid": patient_id},
    )


def _load_latest_session(patient_id: str) -> dict | None:
    return db.query_one(
        """
        SELECT session_id, session_type, status, urgency_level,
               briefing_generated, created_at
        FROM sessions
        WHERE patient_id = CAST(:pid AS uuid)
        ORDER BY created_at DESC
        LIMIT 1
        """,
        {"pid": patient_id},
    )


def _load_conversation(session_id: str) -> list[dict]:
    """Pre-triage conversation turns, oldest first."""
    return db.query(
        """
        SELECT sender, original_text, translated_text, lex_intent, sequence_order
        FROM messages
        WHERE session_id = CAST(:sid AS uuid)
        ORDER BY sequence_order NULLS LAST, created_at
        """,
        {"sid": session_id},
    )


def _load_image_findings(session_id: str) -> list[dict]:
    """Rekognition-derived findings attached to the session."""
    return db.query(
        """
        SELECT detected_condition, body_part, severity_estimate, confidence_score
        FROM image_analyses
        WHERE session_id = CAST(:sid AS uuid)
        ORDER BY uploaded_at
        """,
        {"sid": session_id},
    )


def _format_triage(conversation: list[dict], image_findings: list[dict]) -> str:
    """Render the patient's reported symptoms + image findings for the prompt."""
    lines: list[str] = []
    if conversation:
        lines.append("Pre-triage conversation:")
        for m in conversation:
            text = m.get("translated_text") or m.get("original_text")
            if not text:
                continue
            sender = m.get("sender") or "unknown"
            intent = f"  [intent: {m['lex_intent']}]" if m.get("lex_intent") else ""
            lines.append(f"  - {sender}: {text}{intent}")
    if image_findings:
        lines.append("Image analysis findings:")
        for img in image_findings:
            cond = img.get("detected_condition") or "unspecified finding"
            part = f" on {img['body_part']}" if img.get("body_part") else ""
            sev = f", severity {img['severity_estimate']}" if img.get("severity_estimate") else ""
            conf = (
                f" (confidence {img['confidence_score']})"
                if img.get("confidence_score") is not None
                else ""
            )
            lines.append(f"  - {cond}{part}{sev}{conf}")
    if not lines:
        return "No pre-triage conversation or image findings were recorded."
    return "\n".join(lines)


def _retrieval_query(
    patient: dict,
    session: dict,
    conversation: list[dict],
    image_findings: list[dict],
) -> str:
    """Build a KB query from the patient's actual reported symptoms.

    Falls back to coarse session signals only if no symptom text exists.
    """
    parts: list[str] = []
    for m in conversation:
        text = m.get("translated_text") or m.get("original_text")
        if text:
            parts.append(text)
    for img in image_findings:
        if img.get("detected_condition"):
            part = img.get("body_part") or ""
            parts.append(f"{img['detected_condition']} {part}".strip())

    query = " ".join(parts).strip()
    if query:
        return query
    # Fallback: coarse signals (the old behaviour) when no symptoms recorded.
    coarse = [
        session.get("session_type") or "",
        f"urgency level {session.get('urgency_level')}"
        if session.get("urgency_level") is not None
        else "",
        patient.get("gender") or "",
    ]
    return " ".join(p for p in coarse if p).strip() or "general clinical assessment"


def _persist_briefing(
    patient_id: str,
    session_id: str,
    patient: dict,
    briefing: dict,
    protocol_sources: list[str],
) -> str:
    # session_id is UNIQUE (one briefing per session). Upsert so regenerating a
    # briefing refreshes the existing row instead of colliding, which also makes
    # the function idempotent across re-tests.
    result = db.execute(
        """
        INSERT INTO clinical_briefings
            (briefing_id, patient_id, session_id, chief_complaint,
             patient_context, ai_assessment, recommended_actions, severity,
             protocol_references, processing_status)
        VALUES
            (CAST(:briefing_id AS uuid), CAST(:patient_id AS uuid),
             CAST(:session_id AS uuid), :chief_complaint, :patient_context,
             :ai_assessment, :recommended_actions, :severity,
             :protocol_references, 'complete')
        ON CONFLICT (session_id) DO UPDATE SET
            chief_complaint     = EXCLUDED.chief_complaint,
            patient_context     = EXCLUDED.patient_context,
            ai_assessment       = EXCLUDED.ai_assessment,
            recommended_actions = EXCLUDED.recommended_actions,
            severity            = EXCLUDED.severity,
            protocol_references = EXCLUDED.protocol_references,
            processing_status   = EXCLUDED.processing_status,
            generated_at        = now()
        RETURNING briefing_id
        """,
        {
            "briefing_id": str(uuid.uuid4()),
            "patient_id": patient_id,
            "session_id": session_id,
            "chief_complaint": briefing.get("chief_complaint"),
            "patient_context": json.dumps(patient, default=str),
            "ai_assessment": briefing.get("ai_assessment"),
            "recommended_actions": json.dumps(briefing.get("recommended_actions", [])),
            "severity": briefing.get("severity"),
            "protocol_references": json.dumps(protocol_sources),
        },
    )
    rows = result["rows"]
    briefing_id = rows[0]["briefing_id"] if rows else ""
    # Mark the session so the dashboard knows a briefing exists.
    db.execute(
        "UPDATE sessions SET briefing_generated = true "
        "WHERE session_id = CAST(:sid AS uuid)",
        {"sid": session_id},
    )
    return briefing_id


def handler(event, context):  # noqa: ANN001 - Lambda signature
    try:
        body = parse_body(event)
        patient_id = body.get("patient_id")
        if not patient_id:
            raise BadRequest("patient_id is required")
        patient_id = str(patient_id)

        patient = _load_patient(patient_id)
        if patient is None:
            return error(404, f"Patient {patient_id} not found")

        session = _load_latest_session(patient_id)

        # Walk-in / not pre-triaged: no AI briefing, just surface basic info.
        if session is None or patient.get("intake_method") == "walk_in":
            logger.info(
                "walk_in_no_briefing",
                extra={"extra": {"patient_id": patient_id}},
            )
            return ok(
                {
                    "briefing_generated": False,
                    "reason": "Patient was not pre-triaged (walk-in).",
                    "patient": patient,
                }
            )

        # Pull the patient's actual reported symptoms + image findings.
        conversation = _load_conversation(session["session_id"])
        image_findings = _load_image_findings(session["session_id"])
        triage_text = _format_triage(conversation, image_findings)

        # RAG: retrieve protocols using the real complaint, then generate.
        query_text = _retrieval_query(patient, session, conversation, image_findings)
        passages = bedrock.retrieve_protocols(query_text)
        protocol_context = bedrock.format_protocol_context(passages)
        protocol_sources = [p["source"] for p in passages]

        briefing = bedrock.converse_json(
            system_prompt=prompts.BRIEFING_SYSTEM,
            user_prompt=prompts.build_briefing_prompt(
                patient, session, triage_text, protocol_context
            ),
        )
        # Coerce severity to an allowed DB value so the INSERT can't be rejected
        # by the CHECK constraint, and so the response matches what we store.
        briefing["severity"] = enums.normalize_severity(briefing.get("severity"))

        briefing_id = _persist_briefing(
            patient_id, session["session_id"], patient, briefing, protocol_sources
        )

        return ok(
            {
                "briefing_generated": True,
                "briefing_id": briefing_id,
                "briefing": briefing,
                "disclaimer": prompts.CLINICAL_DISCLAIMER,
                "protocol_sources": protocol_sources,
            }
        )

    except BadRequest as exc:
        return error(400, str(exc))
    except Exception as exc:  # noqa: BLE001 - top-level Lambda guard
        logger.exception("briefing_failed")
        return error(500, f"Failed to generate briefing: {exc}")
