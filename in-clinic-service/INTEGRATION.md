# In-Clinic Service — Integration Contract

**Owner:** Marlon (In-Clinic Service)
**Audience:** Faith (Emergency Pre-Triage), Felista (Non-Emergency Pre-Triage)

The In-Clinic Service is a **consumer** of what the pre-triage services produce.
The handoff happens entirely through the shared Aurora database — there is no
direct service-to-service call. This document is the data contract: what the
In-Clinic briefing/diagnosis Lambdas read, who must produce it, and what happens
if it is missing.

---

## TL;DR — the two things that matter most

1. **Set `patients.intake_method = 'app_triage'`** for any patient you triage
   through the app. If it's `walk_in` (or there is no session), the In-Clinic
   service skips AI and returns `briefing_generated: false`.
2. **Populate `messages.translated_text` (English)** for every triaged session.
   This is what drives both the AI prompt and the English Knowledge Base
   retrieval. Without it, the clinical briefing is thin and low quality.

---

## What the In-Clinic Service READS

### 1. `patients` — created at intake
Read columns: `patient_id, full_name, preferred_language, date_of_birth,
gender, literacy_level, intake_method`.

| Field | Why it matters |
|-------|----------------|
| `intake_method` | **Must be `app_triage`** or no briefing is generated (see TL;DR). |
| `preferred_language` | Feeds the prompt — drives "communicate in the patient's language" guidance. |
| `literacy_level` | Feeds the prompt — drives voice-first / low-literacy guidance. |
| `gender`, `date_of_birth` | Used for clinical context (e.g. obstetric relevance). |

### 2. `sessions` — one per pre-triage interaction
Read columns: `session_id, session_type, urgency_level, status, created_at`.
The In-Clinic service selects the **latest session for the patient by
`created_at`**.

| Field | Why it matters |
|-------|----------------|
| `patient_id` | Links the session to the patient (FK). |
| `urgency_level` | Used in the fallback retrieval query and the prompt. |
| `session_type` | `emergency` / `non_emergency` — included for context. |
| `created_at` | Determines which session is "current". |

### 3. `messages` — the patient conversation (HIGH-VALUE DEPENDENCY)
Read columns: `sender, original_text, translated_text, lex_intent,
sequence_order, created_at`. Linked by `session_id`.

| Field | Why it matters |
|-------|----------------|
| `translated_text` | **Most important.** Preferred over `original_text`; builds the English KB retrieval query. Output of your Transcribe → Translate chain. |
| `original_text` | Fallback if no translation (lower quality — KB protocols are English). |
| `sequence_order` | Used to order the conversation (falls back to `created_at`). Populate at least one. |
| `sender` | Labels who said what in the prompt. |
| `lex_intent` | Optional hint, used if present. |

### 4. `image_analyses` — Rekognition output (OPTIONAL, Felista's flow)
Read columns: `detected_condition, body_part, severity_estimate,
confidence_score`. Linked by `session_id`.

| Field | Why it matters |
|-------|----------------|
| `detected_condition` | Folded into the prompt and retrieval query. |
| `body_part`, `severity_estimate`, `confidence_score` | Added context for the briefing. |

If there are no image rows, the briefing simply omits the image section — no error.

---

## Shared schema contract (CHECK constraint values — all services must agree)

| Table.column | Allowed values |
|--------------|----------------|
| `patients.intake_method` | `app_triage`, `walk_in` |
| `patients.literacy_level` | `standard`, `low_literacy` |
| `sessions.status` | `active`, `completed`, `escalated` |
| `clinical_briefings.severity` | `mild`, `moderate`, `severe`, `critical` |
| `clinical_briefings.processing_status` | `raw`, `partial`, `complete` |
| `clinical_briefings.clinician_decision` | `accepted`, `modified`, `rejected` |

Using any other value triggers a CHECK constraint violation (SQLState 23505/23514).

---

## What the In-Clinic Service WRITES (so we don't collide)

The In-Clinic service writes ONLY to:
- `clinical_briefings` — inserts/upserts keyed on `session_id` (UNIQUE: one
  briefing per session); later updates `clinician_notes`, `ai_diagnosis`,
  `ai_diagnosis_actions`.
- `sessions.briefing_generated` — set to `true` after a briefing is generated.

It treats `patients`, `messages`, and `image_analyses` as **read-only**. Those
are yours to own.

> Note: `clinical_briefings.ai_diagnosis` and `ai_diagnosis_actions` were added
> by migration `migrations/001_add_ai_diagnosis_columns.sql` (additive, nullable
> — does not affect your inserts).

---

## Degradation behavior (what happens when data is missing)

| Condition | In-Clinic service behavior |
|-----------|----------------------------|
| No `patients` row | Returns HTTP 404. |
| No `sessions` row, or `intake_method = 'walk_in'` | Returns `briefing_generated: false` (no AI call). |
| `messages` present but no `translated_text` | Works, but briefing is thin/low quality. |
| No `image_analyses` rows | Fine — image section omitted. |

---

## Correction to the original onboarding brief

The kickoff brief described the handoff as `sessions.triage_summary` /
`sessions.image_analysis` columns. **Those columns do not exist in the live
schema.** The real handoff is:

- patient-reported symptoms → **`messages.translated_text`**
- image findings → **`image_analyses.detected_condition`** (+ related fields)

Please make sure your services write to those, not to a `triage_summary` field.

---

## Quick self-check before you hand a session to In-Clinic

For a session you expect to produce a good briefing, this should all be true:

```sql
-- 1. Patient is app-triaged
SELECT intake_method FROM patients WHERE patient_id = '<id>';        -- 'app_triage'

-- 2. Session exists with urgency + type
SELECT session_id, session_type, urgency_level, created_at
FROM sessions WHERE patient_id = '<id>' ORDER BY created_at DESC LIMIT 1;

-- 3. At least one translated message exists
SELECT count(*) FROM messages
WHERE session_id = '<session_id>' AND translated_text IS NOT NULL;   -- >= 1

-- 4. (Optional) image findings
SELECT detected_condition FROM image_analyses WHERE session_id = '<session_id>';
```


---

# API & Auth Contract (In-Clinic Service ↔ Cognito)

The In-Clinic Service owns its API endpoints. Faith owns Cognito. This is the
contract between the two. Nothing here is built yet on the auth side — it
describes what each side must provide so they integrate without rework.

## Our endpoints

- **Type:** HTTP API (API Gateway v2)
- `POST /briefing`  → `generateClinicalBriefing`
- `POST /diagnosis` → `generateDiagnosticRecommendation`
- JSON in / JSON out. Success = `200`; errors = `{"error": "..."}` with a 4xx/5xx.
- CORS allows the `Authorization` header, so a frontend can send a Bearer token.
- **Auth today:** none (open demo). Adding a Cognito JWT authorizer later needs
  no change to our routes or integrations — it attaches at the gateway.

## Division of responsibility

| Concern | Owner |
|---------|-------|
| Cognito user pool + app client | Faith |
| API Gateway JWT authorizer (token validation at the gateway) | Faith |
| Reading the already-verified `claims.sub` to fill our audit fields | In-Clinic (small handler addition, only once auth is live) |

Token *validation* never happens in our Lambda — the gateway rejects bad tokens
before they reach us. We only ever consume the identity the gateway verified.

## What we will expect from the token (so build the pool accordingly)

- `claims.sub` → the clinician identity. We will match it against
  **`clinicians.cognito_user_id`** to resolve `clinical_briefings.clinician_id`.
- `claims["cognito:username"]` or `claims.email` → display name.

> **Provisioning requirement on Faith's side:** every Cognito user who is a
> clinician must have a row in `clinicians` with `cognito_user_id` = that user's
> Cognito `sub`. Without it we cannot attribute actions (audit `clinician_id`
> stays null).

## What we need from Faith to attach the authorizer

1. **User Pool ID**, **App Client ID**, **Region**.
2. **Token type** the frontend will send (ID token recommended for HTTP API JWT
   authorizers, since `aud` = app client id).

With those, attaching the authorizer to our routes is:
- Issuer: `https://cognito-idp.<region>.amazonaws.com/<userPoolId>`
- Audience: `<app client id>`
- Identity source: `$request.header.Authorization`
- Attach to `POST /briefing` and `POST /diagnosis`.

## Shared conventions (keep all services consistent)

- HTTP API (v2), `POST`, `application/json`.
- Lambda proxy response envelope `{ statusCode, headers, body }` (`body` a JSON string).
- Errors as `{"error": "<message>"}`.
- One shared User Pool / JWT authorizer across all ARIA services (single sign-on).
