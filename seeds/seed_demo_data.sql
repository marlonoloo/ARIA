-- Demo seed data for the In-Clinic Service Lambdas.
--
-- Fixed UUIDs are used so you can paste them straight into the Lambda test
-- events (events/briefing.json, events/diagnosis.json).
--
-- Order matters: patients -> sessions -> clinical_briefings (FK dependencies).
-- All inserts are idempotent via ON CONFLICT DO NOTHING, so re-running is safe.
--
-- IDs:
--   patient (pre-triaged) : 11111111-1111-1111-1111-111111111111
--   patient (walk-in)     : 1111111a-1111-1111-1111-111111111111
--   session               : 22222222-2222-2222-2222-222222222222
--   briefing (for Lambda 2): 33333333-3333-3333-3333-333333333333

-- ---------------------------------------------------------------------------
-- 1. Patient who WAS pre-triaged via the app -> Lambda 1 will call Bedrock.
-- ---------------------------------------------------------------------------
INSERT INTO patients
    (patient_id, full_name, phone_number, preferred_language,
     date_of_birth, gender, literacy_level, intake_method,
     created_at, updated_at)
VALUES
    ('11111111-1111-1111-1111-111111111111',
     'Amara Wanjiku', '+254700000001', 'sw',
     DATE '1994-04-12', 'female', 'low_literacy', 'app_triage',
     now(), now())
ON CONFLICT (patient_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. A walk-in patient -> Lambda 1 returns briefing_generated:false (no AI).
--    Useful for demoing the branch. Optional.
-- ---------------------------------------------------------------------------
INSERT INTO patients
    (patient_id, full_name, phone_number, preferred_language,
     date_of_birth, gender, literacy_level, intake_method,
     created_at, updated_at)
VALUES
    ('1111111a-1111-1111-1111-111111111111',
     'Grace Muthoni', '+254700000002', 'en',
     DATE '1988-09-30', 'female', 'low_literacy', 'walk_in',
     now(), now())
ON CONFLICT (patient_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 3. Pre-triage session for Amara. Lambda 1 loads the latest session by
--    created_at. session_type / status / urgency_level feed the KB query.
-- ---------------------------------------------------------------------------
INSERT INTO sessions
    (session_id, patient_id, started_at, session_type, status,
     urgency_level, briefing_generated, created_at)
VALUES
    ('22222222-2222-2222-2222-222222222222',
     '11111111-1111-1111-1111-111111111111',
     now(), 'emergency', 'active',
     4, false, now())
ON CONFLICT (session_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 4. A ready-made briefing so you can test Lambda 2 (diagnosis) on its own,
--    without first running Lambda 1. If you DO run Lambda 1, it creates its
--    own briefing row with a fresh UUID -- use that one instead.
-- ---------------------------------------------------------------------------
INSERT INTO clinical_briefings
    (briefing_id, patient_id, session_id, chief_complaint, patient_context,
     ai_assessment, recommended_actions, severity, protocol_references,
     processing_status, generated_at)
VALUES
    ('33333333-3333-3333-3333-333333333333',
     '11111111-1111-1111-1111-111111111111',
     '22222222-2222-2222-2222-222222222222',
     'Vaginal bleeding in pregnancy',
     '{"full_name":"Amara Wanjiku","preferred_language":"sw","literacy_level":"low_literacy"}',
     'Possible obstetric emergency; bleeding in pregnancy requires urgent assessment.',
     '["Assess bleeding severity","Escalate to clinician","Prepare for possible referral"]',
     'severe',
     '["who-emergency-triage.md"]',
     'complete', now())
ON CONFLICT (briefing_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Verify
-- ---------------------------------------------------------------------------
-- SELECT patient_id, full_name, intake_method FROM patients
--   WHERE patient_id IN ('11111111-1111-1111-1111-111111111111',
--                        '1111111a-1111-1111-1111-111111111111');
-- SELECT session_id, patient_id, session_type, urgency_level FROM sessions
--   WHERE session_id = '22222222-2222-2222-2222-222222222222';
-- SELECT briefing_id, chief_complaint, severity FROM clinical_briefings
--   WHERE briefing_id = '33333333-3333-3333-3333-333333333333';


-- ===========================================================================
-- 5. PRE-TRIAGE CONTEXT for Amara's session (drives richer briefings).
--
-- IMPORTANT: messages.sender / messages.input_type / image_analyses.severity_estimate
-- may have CHECK constraints we haven't confirmed. Check first:
--
--   SELECT con.conname, pg_get_constraintdef(con.oid)
--   FROM pg_constraint con JOIN pg_class rel ON rel.oid = con.conrelid
--   WHERE rel.relname IN ('messages','image_analyses') AND con.contype = 'c';
--
-- If any value below is rejected, swap it for an allowed one and re-run.
-- ===========================================================================

-- Patient-reported symptoms (Swahili original + English translation).
INSERT INTO messages
    (message_id, session_id, sender, original_text, translated_text,
     detected_language, input_type, lex_intent, sequence_order, created_at)
VALUES
    ('aaaaaaa1-0000-0000-0000-000000000001',
     '22222222-2222-2222-2222-222222222222',
     'patient',
     'Nina damu nyingi na maumivu makali ya tumbo. Nina mimba ya miezi saba.',
     'I have heavy bleeding and severe abdominal pain. I am seven months pregnant.',
     'sw', 'voice', 'ReportEmergency', 1, now()),
    ('aaaaaaa1-0000-0000-0000-000000000002',
     '22222222-2222-2222-2222-222222222222',
     'patient',
     'Damu ilianza saa mbili zilizopita na haikomi.',
     'The bleeding started two hours ago and is not stopping.',
     'sw', 'voice', 'ReportEmergency', 2, now())
ON CONFLICT (message_id) DO NOTHING;

-- Optional: an image finding (uncomment + adjust if severity_estimate is
-- constrained). Left commented because Amara's case is bleeding, not a wound.
-- INSERT INTO image_analyses
--     (image_id, session_id, s3_uri, detected_condition, body_part,
--      severity_estimate, confidence_score, uploaded_at)
-- VALUES
--     ('bbbbbbb1-0000-0000-0000-000000000001',
--      '22222222-2222-2222-2222-222222222222',
--      's3://aria-patient-images/amara/abdo.jpg',
--      'no acute external finding', 'abdomen', 'moderate', 0.82, now())
-- ON CONFLICT (image_id) DO NOTHING;
