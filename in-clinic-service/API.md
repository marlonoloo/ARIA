# In-Clinic Service — Frontend API Contract (for Felista)

This is everything the UI needs to talk to the In-Clinic Service. The shapes
here are stable — build against them. Sample responses for offline development
are in `samples/`.

**Base URL:** `https://jhn2lkbr66.execute-api.us-east-1.amazonaws.com`
**Content type:** `application/json` on every request and response.

---

## How to develop without being blocked

The real endpoints call Bedrock and take **~3–8 seconds**. While building/styling,
**mock against the files in `samples/`** instead of hitting the live API. Switch
to the live Base URL for integration testing. The JSON shape is identical.

So always:
- show a **loading state** (spinner) — responses are slow, this is expected.
- handle the **error shape** (below) for non-200s.

---

## Endpoint 1 — Patient dashboard (review queue)

`GET /patients`

Returns the doctor's review queue, read from the `doctor_dashboard` view:
**clinical briefings the clinician has not yet viewed**, joined to patient,
session, and any image findings, ordered most-urgent-first. Each row already
carries the full briefing, so the UI can render the briefing card straight from
the list — no second call needed to display it.

**Query params (optional):**
- `clinic_id=<uuid>` — only that clinic's queue (default: all clinics).

**Response — HTTP 200:** see `samples/patients_response.json`
```json
{
  "count": 2,
  "patients": [
    {
      "briefing_id": "uuid",
      "patient_id": "uuid",
      "session_id": "uuid",
      "clinic_id": "uuid",
      "patient_name": "string",
      "preferred_language": "sw",
      "interaction_time": "ISO-8601 timestamp",
      "session_type": "emergency | non_emergency",
      "urgency_level": 4,
      "session_status": "active | escalated | completed",
      "chief_complaint": "string",
      "severity": "mild | moderate | severe | critical",
      "ai_assessment": "string",
      "recommended_actions": "JSON-encoded array (string) — JSON.parse before use",
      "protocol_references": "JSON-encoded array (string) — JSON.parse before use",
      "needs_in_person": true,
      "flagged_for_review": true,
      "image_finding": "string or null",
      "image_confidence": 0.88,
      "image_url": "string or null",
      "processing_status": "complete"
    }
  ]
}
```
> Notes:
> - Contains **only briefings not yet viewed by a clinician**, most-urgent-first.
>   Once a briefing is marked viewed, it drops off the queue.
> - `recommended_actions` and `protocol_references` are **JSON-encoded strings** —
>   `JSON.parse()` them before rendering as lists.
> - Use `briefing_id` for `POST /diagnosis`; `patient_id` if you need to
>   (re)generate a briefing via `POST /briefing`.

---

## Endpoint 2 — Clinical briefing

`POST /briefing`

**Request:**
```json
{ "patient_id": "11111111-1111-1111-1111-111111111111" }
```

**Response (briefing generated) — HTTP 200:** see `samples/briefing_response.json`
```json
{
  "briefing_generated": true,
  "briefing_id": "33333333-3333-3333-3333-333333333333",
  "briefing": {
    "chief_complaint": "string — card heading",
    "ai_assessment": "string — main paragraph",
    "recommended_actions": ["string", "..."],
    "severity": "mild | moderate | severe | critical",
    "protocol_sources": ["model's labels for protocols it used"],
    "uncertainty_notes": "string or null — show as a caveat box if present"
  },
  "disclaimer": "string — show as a footer on every briefing",
  "protocol_sources": ["actual source document URIs — use THESE for citations"]
}
```

**Response (walk-in / not pre-triaged) — HTTP 200:** see `samples/briefing_walkin.json`
```json
{
  "briefing_generated": false,
  "reason": "Patient was not pre-triaged (walk-in).",
  "patient": { "...": "basic patient fields" }
}
```
> The UI must handle BOTH 200 shapes. Branch on `briefing_generated`: if `false`,
> show "no AI briefing — walk-in" and just the basic patient info.

---

## Endpoint 3 — Diagnostic recommendation

`POST /diagnosis`

**Request:**
```json
{
  "briefing_id": "33333333-3333-3333-3333-333333333333",
  "clinician_remarks": "BP 150/95, oedema, headache at 30 weeks"
}
```
`briefing_id` is the value returned by `/briefing`. `clinician_remarks` is the
free text the doctor types after examining the patient.

**Response — HTTP 200:** see `samples/diagnosis_response.json`
```json
{
  "briefing_id": "33333333-3333-3333-3333-333333333333",
  "diagnosis": {
    "ai_diagnosis": "string — heading/summary",
    "ai_diagnosis_actions": ["string", "..."],
    "severity": "mild | moderate | severe | critical",
    "agreement_with_clinician": "aligns | diverges | unclear",
    "divergence_note": "string or null",
    "protocol_sources": ["model's labels"]
  },
  "disclaimer": "string — footer",
  "protocol_sources": ["actual source document URIs"]
}
```
> **Important UI behaviour:** when `agreement_with_clinician` is `"diverges"`,
> render `divergence_note` as a prominent **warning banner**. This is the key
> safety story — the AI flagging that its recommendation differs from the
> clinician's findings.

---

## Field display guide

| Field | UI treatment |
|-------|--------------|
| `severity` | colored badge: mild=green, moderate=amber, severe=orange, critical=red |
| `chief_complaint` / `ai_diagnosis` | card heading |
| `ai_assessment` | body paragraph |
| `recommended_actions` / `ai_diagnosis_actions` | checklist / ordered list |
| `agreement_with_clinician` | normal if `aligns`; warning banner if `diverges` |
| `divergence_note` | the warning banner text |
| `uncertainty_notes` | muted caveat box (only if non-null) |
| top-level `protocol_sources` | "Sources" footer (these are the real document URIs) |
| `disclaimer` | persistent footer on every AI output |

> Note: there are two `protocol_sources` — one **inside** `briefing`/`diagnosis`
> (the model's own labels) and one at the **top level** (the actual source
> document URIs). For citations, use the **top-level** one.

---

## Errors

Any non-200 returns:
```json
{ "error": "human-readable message" }
```
| Status | Meaning | Suggested UI |
|--------|---------|--------------|
| 400 | bad/missing input (e.g. no `patient_id`) | inline form error |
| 404 | patient or briefing not found | "not found" message |
| 500 | server/Bedrock/DB failure | "something went wrong, retry" |

---

## CORS & auth

- CORS is handled at the API Gateway. Allowed: origin `*` (will be tightened to
  the dashboard's domain), methods `POST, OPTIONS`, headers
  `content-type, authorization`.
- **Auth today:** none — call the endpoints directly.
- **Later (Faith's Cognito):** the UI will send `Authorization: Bearer <token>`
  on every request. Build the fetch wrapper so adding that header is a one-line
  change (e.g. read an optional token from app state). Nothing else changes.

---

## What the UI needs to create (suggested screens)

1. **Patient queue** — call `GET /patients` to populate the worklist. Each row
   already includes the full briefing, so you can render the briefing card
   directly from the selected row (no extra call needed to display it).
2. **Briefing view** — clinical card (heading, severity badge, assessment,
   actions, sources, disclaimer). `POST /briefing` is used to (re)generate a
   briefing for a `patient_id` when needed; for the walk-in case it returns
   `briefing_generated: false`.
3. **Examination remarks** — a text box; on submit, call `/diagnosis` with the
   `briefing_id` + remarks.
4. **Diagnosis view** — recommendation card, with the **divergence banner** when
   `agreement_with_clinician = "diverges"`.

---

## Endpoints summary

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/patients` | Doctor's review queue (un-viewed briefings, urgent first) |
| POST | `/briefing` | Generate the pre-exam clinical briefing |
| POST | `/diagnosis` | Generate the diagnostic recommendation |
| POST | `/briefing/reviewed` | Mark a briefing reviewed (removes it from the queue) |

---

## Endpoint 4 — Mark briefing reviewed

`POST /briefing/reviewed`

Marks a briefing as reviewed by the clinician, which removes it from the
`GET /patients` queue (that queue only shows un-viewed briefings). This is what
the dashboard's "Dismiss" button should call so the card stays gone after a
refresh.

**Request:**
```json
{ "briefing_id": "33333333-3333-3333-3333-333333333333" }
```
Optional: include `"clinician_id": "<uuid>"` to record who reviewed it.

**Response — HTTP 200:**
```json
{ "briefing_id": "33333333-3333-3333-3333-333333333333", "reviewed": true }
```
Returns `404` if the `briefing_id` doesn't exist, `400` if it's missing.

> UI note: call this from `markReviewed()` **before** removing the card, so the
> dismissal persists. On success, drop the card; on failure, leave it and show
> an error.
