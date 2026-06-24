"""Lambda 2: generateDiagnosticRecommendation.

Trigger: POST /diagnosis  (doctor submits examination remarks)

Flow:
  1. Load the existing briefing (+ its patient) from Aurora by briefing_id.
  2. Retrieve clinical protocols relevant to remarks + complaint.
  3. Ask Claude for a structured diagnostic recommendation.
  4. Persist the clinician's remarks (clinician_notes) and the AI diagnosis
     (ai_diagnosis, ai_diagnosis_actions) and return the recommendation.

Schema note: the clinician's accept/modify/reject decision is recorded by a
separate write (the doctor acts on what this function returns via
clinician_decision / clinician_modified_recommendation). This function only
produces the AI recommendation and stores the remarks that prompted it.

Requires the additive columns ai_diagnosis / ai_diagnosis_actions on
clinical_briefings (see migrations/001_add_ai_diagnosis_columns.sql).
"""
from __future__ import annotations

import json

from shared import bedrock, db, prompts
from shared.http import BadRequest, error, ok, parse_body
from shared.logging_utils import get_logger

logger = get_logger("generateDiagnosticRecommendation")


def _load_briefing(briefing_id: str) -> dict | None:
    return db.query_one(
        """
        SELECT b.briefing_id, b.patient_id, b.session_id, b.chief_complaint,
               b.ai_assessment, b.recommended_actions, b.severity,
               p.full_name, p.preferred_language, p.literacy_level
        FROM clinical_briefings b
        JOIN patients p ON p.patient_id = b.patient_id
        WHERE b.briefing_id = CAST(:bid AS uuid)
        """,
        {"bid": briefing_id},
    )


def _retrieval_query(briefing: dict, remarks: str) -> str:
    parts = [remarks, briefing.get("chief_complaint") or ""]
    return " ".join(p for p in parts if p).strip() or "general clinical assessment"


def _persist_diagnosis(briefing_id: str, remarks: str, diagnosis: dict) -> None:
    db.execute(
        """
        UPDATE clinical_briefings
        SET clinician_notes = :remarks,
            ai_diagnosis = :ai_diagnosis,
            ai_diagnosis_actions = :ai_diagnosis_actions
        WHERE briefing_id = CAST(:bid AS uuid)
        """,
        {
            "bid": briefing_id,
            "remarks": remarks,
            "ai_diagnosis": diagnosis.get("ai_diagnosis"),
            "ai_diagnosis_actions": json.dumps(diagnosis.get("ai_diagnosis_actions", [])),
        },
    )


def handler(event, context):  # noqa: ANN001 - Lambda signature
    try:
        body = parse_body(event)
        briefing_id = body.get("briefing_id")
        remarks = (body.get("clinician_remarks") or "").strip()
        if not briefing_id:
            raise BadRequest("briefing_id is required")
        if not remarks:
            raise BadRequest("clinician_remarks is required")
        briefing_id = str(briefing_id)

        briefing = _load_briefing(briefing_id)
        if briefing is None:
            return error(404, f"Briefing {briefing_id} not found")

        patient = {
            "full_name": briefing.get("full_name"),
            "preferred_language": briefing.get("preferred_language"),
            "literacy_level": briefing.get("literacy_level"),
        }
        prior_briefing = {
            "chief_complaint": briefing.get("chief_complaint"),
            "ai_assessment": briefing.get("ai_assessment"),
            "recommended_actions": briefing.get("recommended_actions"),
            "severity": briefing.get("severity"),
        }

        query_text = _retrieval_query(briefing, remarks)
        passages = bedrock.retrieve_protocols(query_text)
        protocol_context = bedrock.format_protocol_context(passages)

        diagnosis = bedrock.converse_json(
            system_prompt=prompts.DIAGNOSIS_SYSTEM,
            user_prompt=prompts.build_diagnosis_prompt(
                patient, prior_briefing, remarks, protocol_context
            ),
        )

        _persist_diagnosis(briefing_id, remarks, diagnosis)

        return ok(
            {
                "briefing_id": briefing_id,
                "diagnosis": diagnosis,
                "disclaimer": prompts.CLINICAL_DISCLAIMER,
                "protocol_sources": [p["source"] for p in passages],
            }
        )

    except BadRequest as exc:
        return error(400, str(exc))
    except Exception as exc:  # noqa: BLE001 - top-level Lambda guard
        logger.exception("diagnosis_failed")
        return error(500, f"Failed to generate diagnosis: {exc}")
