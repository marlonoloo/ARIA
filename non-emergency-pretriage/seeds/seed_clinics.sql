-- Seed a spread of active clinics with real coordinates so nearest-clinic
-- routing returns meaningful, varied results (previously only Mothobi Central
-- in Nairobi existed, so every lookup returned it at ~0 km).
--
-- Columns match what nearest_clinic() in chat_functionality.py selects/filters:
--   clinic_name, location, latitude, longitude, is_active, services_available (text[])
--
-- Idempotent: fixed UUIDs + ON CONFLICT (clinic_id) DO NOTHING, safe to re-run.
-- Single multi-row INSERT so it runs as one statement via the RDS Data API.

INSERT INTO clinics
    (clinic_id, clinic_name, location, latitude, longitude, is_active, services_available)
VALUES
    ('a1000000-0000-0000-0000-000000000001', 'Mothobi Westlands Clinic',  'Westlands, Nairobi', -1.2649, 36.8025, true, ARRAY['general','pediatrics']),
    ('a1000000-0000-0000-0000-000000000002', 'Mothobi Mombasa Clinic',    'Mombasa',            -4.0435, 39.6682, true, ARRAY['general','maternity','burns']),
    ('a1000000-0000-0000-0000-000000000003', 'Mothobi Kisumu Clinic',     'Kisumu',             -0.0917, 34.7680, true, ARRAY['general','maternity']),
    ('a1000000-0000-0000-0000-000000000004', 'Mothobi Nakuru Clinic',     'Nakuru',             -0.3031, 36.0800, true, ARRAY['general','pediatrics','burns']),
    ('a1000000-0000-0000-0000-000000000005', 'Mothobi Eldoret Clinic',    'Eldoret',             0.5143, 35.2698, true, ARRAY['general']),
    ('a1000000-0000-0000-0000-000000000006', 'Mothobi Thika Maternity',   'Thika',              -1.0333, 37.0693, true, ARRAY['general','maternity','pediatrics']),
    ('a1000000-0000-0000-0000-000000000007', 'Mothobi Nyeri Clinic',      'Nyeri',              -0.4169, 36.9514, true, ARRAY['general','burns'])
ON CONFLICT (clinic_id) DO NOTHING;
