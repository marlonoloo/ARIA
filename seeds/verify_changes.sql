-- Verification queries for the In-Clinic Service.
-- Run these in the RDS Query Editor after the migration, the seed, and after
-- invoking the Lambdas. Each block says what a PASS looks like.

-- ===========================================================================
-- A. MIGRATION 001 — did the ai_diagnosis columns get added?
-- PASS: two rows returned (ai_diagnosis, ai_diagnosis_actions), both text.
-- ===========================================================================
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'clinical_briefings'
  AND column_name IN ('ai_diagnosis', 'ai_diagnosis_actions')
ORDER BY column_name;

-- ===========================================================================
-- B. SEED DATA — did the demo rows land?
-- ===========================================================================

-- B1. Patients: PASS = 2 rows, Amara = app_triage, Grace = walk_in.
SELECT patient_id, full_name, intake_method, preferred_language
FROM patients
WHERE patient_id IN ('11111111-1111-1111-1111-111111111111',
                     '1111111a-1111-1111-1111-111111111111')
ORDER BY full_name;

-- B2. Session: PASS = 1 row, session_type=emergency, urgency_level=4.
SELECT session_id, patient_id, session_type, status,
       urgency_level, briefing_generated
FROM sessions
WHERE session_id = '22222222-2222-2222-2222-222222222222';

-- B3. Seeded briefing for Lambda 2: PASS = 1 row, severity=high.
SELECT briefing_id, chief_complaint, severity, processing_status
FROM clinical_briefings
WHERE briefing_id = '33333333-3333-3333-3333-333333333333';

-- ===========================================================================
-- C. AFTER RUNNING LAMBDA 1 (generateClinicalBriefing)
-- ===========================================================================

-- C1. A NEW briefing row should exist for Amara (the one the Lambda generated,
--     with its own fresh UUID — not the seeded 3333... row).
-- PASS: at least one row whose briefing_id is NOT the seeded one.
SELECT briefing_id, chief_complaint, severity, processing_status,
       protocol_references, generated_at
FROM clinical_briefings
WHERE patient_id = '11111111-1111-1111-1111-111111111111'
  AND briefing_id <> '33333333-3333-3333-3333-333333333333'
ORDER BY generated_at DESC;

-- C2. The session should now be flagged as briefed.
-- PASS: briefing_generated = true.
SELECT session_id, briefing_generated
FROM sessions
WHERE session_id = '22222222-2222-2222-2222-222222222222';

-- ===========================================================================
-- D. AFTER RUNNING LAMBDA 2 (generateDiagnosticRecommendation)
--    Replace <BRIEFING_ID> with the briefing_id you sent in the test event
--    (the seeded 3333... row, or a new one from Lambda 1).
-- PASS: clinician_notes populated AND ai_diagnosis / ai_diagnosis_actions
--       populated (non-null).
-- ===========================================================================
SELECT briefing_id,
       clinician_notes,
       ai_diagnosis,
       ai_diagnosis_actions
FROM clinical_briefings
WHERE briefing_id = '33333333-3333-3333-3333-333333333333';

-- ===========================================================================
-- E. Quick all-in-one snapshot of Amara's records (handy during the demo).
-- ===========================================================================
SELECT b.briefing_id, b.severity, b.processing_status,
       b.ai_diagnosis IS NOT NULL AS has_diagnosis,
       b.clinician_notes IS NOT NULL AS has_remarks,
       b.generated_at
FROM clinical_briefings b
WHERE b.patient_id = '11111111-1111-1111-1111-111111111111'
ORDER BY b.generated_at DESC;
