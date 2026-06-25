"""Lambda 5: finalizeConsultation.

Trigger: POST /consultation/finalize  (doctor completes the consultation)

Records the clinician's decision on the AI recommendation, saves any
prescriptions and an optional follow-up appointment, then composes a
plain-language patient summary, translates it into the patient's language, and
stores it as a DRAFT patient notification (sent=false, approved_by_doctor=false)
for the doctor to review before sending.

Nothing is sent to the patient here — that requires a separate, explicit
approval step (POST /notification/send). This preserves the "doctor approves
before anything reaches the patient" safety rule.
"""
from __future__ import annotations

import uuid

from shared import db, notifications
from shared.http import BadRequest, error, ok, parse_body
from shared.logging_utils import get_logger

logger = get_logger("finalizeConsultation")

_DECISIONS = ("accepted", "modified", "rejected")


def _load_briefing_patient(briefing_id: str) -> dict | None:
    return db.query_one(
        """
        SELECT b.briefing_id, b.session_id, b.patient_id, b.chief_complaint,
               b.ai_diagnosis, p.full_name, p.preferred_language, p.email
        FROM clinical_briefings b
        JOIN patients p ON p.patient_id = b.patient_id
        WHERE b.briefing_id = CAST(:bid AS uuid)
        """,
        {"bid": briefing_id},
    )


def _update_decision(briefing_id, decision, modified_rec, notes):
    db.execute(
        """
        UPDATE clinical_briefings
        SET clinician_decision = :decision,
            clinician_agrees = :agrees,
            clinician_modified_recommendation =
                COALESCE(:modified_rec, clinician_modified_recommendation),
            clinician_notes = COALESCE(:notes, clinician_notes)
        WHERE briefing_id = CAST(:bid AS uuid)
        """,
        {
            "bid": briefing_id,
            "decision": decision,
            "agrees": decision == "accepted",
            "modified_rec": modified_rec,
            "notes": notes,
        },
    )


def _insert_prescription(briefing_id, patient_id, clinician_id, rx):
    db.execute(
        """
        INSERT INTO prescriptions
            (briefing_id, patient_id, clinician_id, drug_name, dosage,
             frequency, duration, instructions)
        VALUES
            (CAST(:bid AS uuid), CAST(:pid AS uuid), CAST(:cid AS uuid),
             :drug_name, :dosage, :frequency, :duration, :instructions)
        """,
        {
            "bid": briefing_id,
            "pid": patient_id,
            "cid": clinician_id,
            "drug_name": rx.get("drug_name"),
            "dosage": rx.get("dosage"),
            "frequency": rx.get("frequency"),
            "duration": rx.get("duration"),
            "instructions": rx.get("instructions"),
        },
    )


def _insert_appointment(patient_id, briefing_id, clinician_id, follow_up):
    db.execute(
        """
        INSERT INTO appointments
            (patient_id, briefing_id, scheduled_date, reason, created_by)
        VALUES
            (CAST(:pid AS uuid), CAST(:bid AS uuid), CAST(:date AS date),
             :reason, CAST(:cid AS uuid))
        """,
        {
            "pid": patient_id,
            "bid": briefing_id,
            "date": follow_up.get("scheduled_date"),
            "reason": follow_up.get("reason"),
            "cid": clinician_id,
        },
    )


def _insert_notification(notification_id, session_id, patient_id, english, translated, language, recipient):
    db.execute(
        """
        INSERT INTO patient_notifications
            (notification_id, session_id, patient_id, content_text,
             translated_text, language, channel, recipient,
             approved_by_doctor, sent)
        VALUES
            (CAST(:nid AS uuid), CAST(:sid AS uuid), CAST(:pid AS uuid),
             :content, :translated, :language, 'email', :recipient,
             false, false)
        """,
        {
            "nid": notification_id,
            "sid": session_id,
            "pid": patient_id,
            "content": english,
            "translated": translated,
            "language": language,
            "recipient": recipient,
        },
    )


def _compose_summary(name, diagnosis_text, prescriptions, follow_up):
    lines = [f"Dear {name},", "", "Here is a summary of your clinic visit."]
    if diagnosis_text:
        lines += ["", f"Assessment: {diagnosis_text}"]
    rx_lines = []
    for rx in prescriptions:
        if not rx.get("drug_name"):
            continue
        parts = [rx["drug_name"], rx.get("dosage"), rx.get("frequency")]
        if rx.get("duration"):
            parts.append(f"for {rx['duration']}")
        line = " ".join(p for p in parts if p)
        if rx.get("instructions"):
            line += f" ({rx['instructions']})"
        rx_lines.append(f"- {line}")
    if rx_lines:
        lines += ["", "Your medication:"] + rx_lines
    if follow_up.get("scheduled_date"):
        fu = f"Follow-up visit: {follow_up['scheduled_date']}"
        if follow_up.get("reason"):
            fu += f" — {follow_up['reason']}"
        lines += ["", fu]
    lines += [
        "",
        "Please follow these instructions. If your symptoms get worse, return to the clinic or call us.",
        "",
        "Mothobi Healthcare Group",
    ]
    return "\n".join(lines)


def handler(event, context):  # noqa: ANN001
    try:
        body = parse_body(event)
        briefing_id = body.get("briefing_id")
        decision = (body.get("clinician_decision") or "").strip().lower()
        if not briefing_id:
            raise BadRequest("briefing_id is required")
        if decision not in _DECISIONS:
            raise BadRequest(f"clinician_decision must be one of: {', '.join(_DECISIONS)}")
        briefing_id = str(briefing_id)

        rec = _load_briefing_patient(briefing_id)
        if rec is None:
            return error(404, f"Briefing {briefing_id} not found")

        clinician_id = body.get("clinician_id") or None
        modified_rec = body.get("clinician_modified_recommendation")
        notes = body.get("clinician_notes")
        prescriptions = body.get("prescriptions") or []
        follow_up = body.get("follow_up") or {}
        recipient = body.get("recipient_email") or rec.get("email")

        # 1. Record the clinician's decision.
        _update_decision(briefing_id, decision, modified_rec, notes)

        # 2. Save prescriptions (skip entries without a drug name).
        saved_rx = 0
        for rx in prescriptions:
            if rx.get("drug_name"):
                _insert_prescription(briefing_id, rec["patient_id"], clinician_id, rx)
                saved_rx += 1

        # 3. Save optional follow-up appointment.
        follow_up_saved = False
        if follow_up.get("scheduled_date"):
            _insert_appointment(rec["patient_id"], briefing_id, clinician_id, follow_up)
            follow_up_saved = True

        # 4. Compose + translate the patient summary, store as a draft.
        diagnosis_text = (
            modified_rec if (decision == "modified" and modified_rec)
            else rec.get("ai_diagnosis") or rec.get("chief_complaint")
        )
        english = _compose_summary(rec["full_name"], diagnosis_text, prescriptions, follow_up)
        language = rec.get("preferred_language") or "en"
        translated = notifications.translate_text(english, language)

        notification_id = str(uuid.uuid4())
        _insert_notification(
            notification_id, rec.get("session_id"), rec["patient_id"],
            english, translated, language, recipient,
        )

        return ok(
            {
                "briefing_id": briefing_id,
                "decision": decision,
                "prescriptions_saved": saved_rx,
                "follow_up_scheduled": follow_up_saved,
                "notification_id": notification_id,
                "recipient": recipient,
                "language": language,
                "summary_en": english,
                "summary_translated": translated,
                "note": "Draft only — call POST /notification/send to deliver after review.",
            }
        )

    except BadRequest as exc:
        return error(400, str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("finalize_failed")
        return error(500, f"Failed to finalize consultation: {exc}")
