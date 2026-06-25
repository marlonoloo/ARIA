-- Migration 002: expose patient_id and session_id on the doctor_dashboard view.
--
-- The In-Clinic dashboard endpoint (GET /patients) reads from doctor_dashboard,
-- but the view did not expose patient_id / session_id, which the frontend needs
-- to navigate (e.g. call POST /briefing for a patient, reference the session).
--
-- This is ADDITIVE and SAFE for other consumers: CREATE OR REPLACE VIEW only
-- permits appending columns to the end of the select list, so existing column
-- positions are unchanged. The view's filter (un-viewed briefings) and ordering
-- (urgency desc) are preserved exactly.

CREATE OR REPLACE VIEW doctor_dashboard AS
SELECT cb.briefing_id,
    s.assigned_clinic_id AS clinic_id,
    cb.processing_status,
    p.full_name AS patient_name,
    p.preferred_language,
    s.started_at AS interaction_time,
    s.session_type,
    s.urgency_level,
    s.status AS session_status,
    cb.chief_complaint,
    cb.severity,
    cb.ai_assessment,
    cb.recommended_actions,
    cb.protocol_references,
    cb.needs_in_person,
    cb.flagged_for_review,
    ia.detected_condition AS image_finding,
    ia.confidence_score AS image_confidence,
    ia.s3_uri AS image_url,
    -- Appended columns (migration 002):
    cb.patient_id,
    s.session_id
   FROM clinical_briefings cb
     JOIN sessions s ON cb.session_id = s.session_id
     JOIN patients p ON cb.patient_id = p.patient_id
     LEFT JOIN image_analyses ia ON s.session_id = ia.session_id
  WHERE cb.viewed_by_clinician = false
  ORDER BY s.urgency_level DESC NULLS LAST, s.started_at;
