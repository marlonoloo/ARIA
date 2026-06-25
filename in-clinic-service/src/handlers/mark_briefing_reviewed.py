"""Lambda 4: markBriefingReviewed.

Trigger: POST /briefing/reviewed  (doctor dismisses / finishes a briefing)

Sets viewed_by_clinician = true (and viewed_at = now()) on a briefing, which
removes it from the doctor_dashboard view (that view filters on
viewed_by_clinician = false). This is what makes the dashboard "Dismiss" button
persist across refreshes.

Optionally records who reviewed it: pass `clinician_id` in the body, or — once a
Cognito JWT authorizer is attached — it can be read from the verified claims.
"""
from __future__ import annotations

from shared import db
from shared.http import BadRequest, error, ok, parse_body
from shared.logging_utils import get_logger

logger = get_logger("markBriefingReviewed")


def _mark_reviewed(briefing_id: str, clinician_id: str | None) -> int:
    result = db.execute(
        """
        UPDATE clinical_briefings
        SET viewed_by_clinician = true,
            viewed_at = now(),
            clinician_id = COALESCE(CAST(:clinician_id AS uuid), clinician_id)
        WHERE briefing_id = CAST(:bid AS uuid)
        """,
        {"bid": briefing_id, "clinician_id": clinician_id},
    )
    return result["rows_updated"]


def handler(event, context):  # noqa: ANN001 - Lambda signature
    try:
        body = parse_body(event)
        briefing_id = body.get("briefing_id")
        if not briefing_id:
            raise BadRequest("briefing_id is required")
        clinician_id = body.get("clinician_id") or None

        updated = _mark_reviewed(str(briefing_id), clinician_id)
        if updated == 0:
            return error(404, f"Briefing {briefing_id} not found")

        logger.info(
            "briefing_marked_reviewed",
            extra={"extra": {"briefing_id": briefing_id}},
        )
        return ok({"briefing_id": briefing_id, "reviewed": True})

    except BadRequest as exc:
        return error(400, str(exc))
    except Exception as exc:  # noqa: BLE001 - top-level Lambda guard
        logger.exception("mark_reviewed_failed")
        return error(500, f"Failed to mark briefing reviewed: {exc}")
