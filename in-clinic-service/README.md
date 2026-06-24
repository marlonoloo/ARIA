# Project ARIA — In-Clinic Service

Part of **Project ARIA** (Accessible Real-time Intelligent Assistant), a
multi-modal AI healthcare assistant for the fictional **Mothobi Healthcare
Group**. This repository is the **In-Clinic Service**: once a patient arrives at
the clinic, it generates an AI clinical briefing for the clinician, then a
diagnostic recommendation after the clinician examines the patient.

> AWS Tech U capstone (Group 3). Proof-of-concept — not for real clinical use.

## What it does

```
Patient pre-triaged (app)         Doctor at clinic
        │                                │
        ▼                                ▼
  messages / image_analyses   ──►  generateClinicalBriefing  (Bedrock + RAG)
  (from pre-triage services)              │
                                          ▼
                                  Doctor reads briefing, examines patient,
                                  types remarks
                                          │
                                          ▼
                              generateDiagnosticRecommendation (Bedrock + RAG)
                                          │
                                          ▼
                              Doctor accepts / modifies / rejects
```

Both AI calls are **grounded via Retrieval-Augmented Generation** against a
Bedrock Knowledge Base of clinical protocols (WHO MCPC + Mothobi protocols), and
all output is **decision support for a licensed clinician** — never autonomous.

## AWS services

Amazon Bedrock (Claude, Converse API) · Bedrock Knowledge Bases (managed RAG) ·
AWS Lambda · Amazon Aurora Serverless v2 PostgreSQL (via RDS Data API) ·
Amazon S3 (KB source docs).

## Repository layout

| Path | What |
|------|------|
| `src/handlers/clinical_briefing.py` | Lambda 1 — `generateClinicalBriefing` |
| `src/handlers/diagnostic_recommendation.py` | Lambda 2 — `generateDiagnosticRecommendation` |
| `src/shared/` | Shared modules: `bedrock`, `db`, `config`, `prompts`, `enums`, `http`, `logging_utils` |
| `knowledge-base/protocols/` | Sample clinical protocol docs for the KB |
| `knowledge-base/SETUP.md` | How to set up the Bedrock Knowledge Base + Lambda config + IAM |
| `migrations/` | Additive schema changes (`001_add_ai_diagnosis_columns.sql`) |
| `seeds/` | Demo data + verification queries |
| `events/` | Sample Lambda test events |
| `scripts/package.sh` | Build a per-Lambda deployment zip |
| `tests/` | Unit tests (handlers, enums, JSON parsing) |
| `INTEGRATION.md` | **Data contract for teammates** (pre-triage services) |

## Quick start

1. **Database** — apply `migrations/001_add_ai_diagnosis_columns.sql`, then load
   `seeds/seed_demo_data.sql`.
2. **Knowledge Base** — follow `knowledge-base/SETUP.md`.
3. **Build** — `scripts/package.sh clinical_briefing` and
   `scripts/package.sh diagnostic_recommendation`.
4. **Deploy** — upload each zip to its Lambda; set the env vars and IAM policy
   from `SETUP.md`; handler strings are `handlers.<name>.handler`.
5. **Test** — invoke with the events in `events/`; verify with
   `seeds/verify_changes.sql`.

## Configuration (Lambda environment variables)

| Variable | Notes |
|----------|-------|
| `DB_CLUSTER_ARN` | Aurora cluster ARN (full ARN, not the name) |
| `DB_SECRET_ARN` | Secrets Manager ARN for the cluster credentials |
| `DB_NAME` | defaults to `aria` |
| `KB_ID` | Bedrock Knowledge Base ID |
| `BEDROCK_MODEL_ID` | active model / inference-profile ID, e.g. `us.anthropic.claude-sonnet-4-20250514-v1:0` |
| `KB_NUM_RESULTS` | optional, default 5 |

No secrets are stored in this repo — all credentials come from environment
variables and Secrets Manager at runtime.

## Tests

```bash
pip install -r requirements.txt
PYTHONPATH=src python -m pytest tests/ -v
```

## Teammates

If you own a pre-triage service, read **[`INTEGRATION.md`](./INTEGRATION.md)** —
it specifies exactly what this service reads from the shared database.
