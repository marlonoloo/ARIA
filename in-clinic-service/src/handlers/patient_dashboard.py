"""Lambda 3: patientDashboard.

Trigger: GET /patients  (doctor opens the dashboard)

Returns the doctor's review queue straight from the `doctor_dashboard` view:
clinical briefings the clinician has NOT yet viewed, joined to patient + session
+ image findings, ordered most-urgent-first. Selecting a row gives the UI the
`patient_id` / `session_id` / `briefing_id` it needs.

Reading from the shared view keeps the dashboard's join/filter/sort logic in one
place (the DB) that the whole team can see. Requires migration 002, which adds
patient_id + session_id to the view.

Optional query param:
  - clinic_id=<uuid>  → only that clinic's queue (default: all clinics).
"""
from __future__ import annotations

from shared import db
from shared.http import error, ok
from shared.logging_utils import get_logger

logger = get_logger("patientDashboard")


def _load_dashboard(clinic_id: str | None) -> list[dict]:
    where = "WHERE clinic_id = CAST(:cid AS uuid)" if clinic_id else ""
    params = {"cid": clinic_id} if clinic_id else None
    return db.query(
        f"""
        SELECT briefing_id, patient_id, session_id, clinic_id, patient_name,
               preferred_language, interaction_time, session_type, urgency_level,
               session_status, chief_complaint, severity, ai_assessment,
               recommended_actions, protocol_references, needs_in_person,
               flagged_for_review, image_finding, image_confidence, image_url,
               processing_status
        FROM doctor_dashboard
        {where}
        ORDER BY urgency_level DESC NULLS LAST, interaction_time
        """,
        params,
    )


def handler(event, context):  # noqa: ANN001 - Lambda signature
    try:
        params = (event or {}).get("queryStringParameters") or {}
        clinic_id = params.get("clinic_id") or None
        rows = _load_dashboard(clinic_id)
        logger.info("dashboard_loaded", extra={"extra": {"count": len(rows)}})
        return ok({"count": len(rows), "patients": rows})
    except Exception as exc:  # noqa: BLE001 - top-level Lambda guard
        logger.exception("dashboard_failed")
        return error(500, f"Failed to load dashboard: {exc}")
