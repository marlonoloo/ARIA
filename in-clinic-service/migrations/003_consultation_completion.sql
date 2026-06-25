-- Migration 003: complete the clinical journey (prescriptions, follow-ups,
-- and patient email notifications).
--
-- Additive and safe: new tables + new nullable columns only. Nothing existing
-- is altered or dropped, so the pre-triage services are unaffected.

-- ---------------------------------------------------------------------------
-- 1. Patient email (for SES notifications). Nullable; seed a verified SES
--    address for demo patients.
-- ---------------------------------------------------------------------------
ALTER TABLE patients
    ADD COLUMN IF NOT EXISTS email varchar(320);

-- ---------------------------------------------------------------------------
-- 2. Prescriptions — one row per drug (a consultation can have several).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prescriptions (
    prescription_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    briefing_id     uuid REFERENCES clinical_briefings(briefing_id),
    patient_id      uuid REFERENCES patients(patient_id),
    clinician_id    uuid REFERENCES clinicians(clinician_id),
    drug_name       text NOT NULL,
    dosage          text,
    frequency       text,
    duration        text,
    instructions    text,
    created_at      timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_prescriptions_briefing ON prescriptions(briefing_id);
CREATE INDEX IF NOT EXISTS idx_prescriptions_patient  ON prescriptions(patient_id);

-- ---------------------------------------------------------------------------
-- 3. Appointments — optional follow-up visit per consultation.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS appointments (
    appointment_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id      uuid REFERENCES patients(patient_id),
    clinic_id       uuid REFERENCES clinics(clinic_id),
    briefing_id     uuid REFERENCES clinical_briefings(briefing_id),
    scheduled_date  date NOT NULL,
    reason          text,
    status          varchar(20) DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'completed', 'cancelled')),
    created_by      uuid REFERENCES clinicians(clinician_id),
    created_at      timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_appointments_patient ON appointments(patient_id);

-- ---------------------------------------------------------------------------
-- 4. Patient notifications — add fields for translation + email delivery.
--    content_text (existing) holds the English summary; translated_text holds
--    what is actually sent in the patient's language.
-- ---------------------------------------------------------------------------
ALTER TABLE patient_notifications
    ADD COLUMN IF NOT EXISTS translated_text text,
    ADD COLUMN IF NOT EXISTS language        varchar(10),
    ADD COLUMN IF NOT EXISTS channel         varchar(20) DEFAULT 'email',
    ADD COLUMN IF NOT EXISTS recipient       text,
    ADD COLUMN IF NOT EXISTS sent_at         timestamptz;
