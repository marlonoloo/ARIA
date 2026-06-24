# Project ARIA — AWS Tech U Capstone (Group 3)

**Project ARIA** (Accessible Real-time Intelligent Assistant) is a multi-modal
AI healthcare assistant for the fictional **Mothobi Healthcare Group**, a
network of clinics serving patients across Africa with significant language and
literacy barriers.

> Proof-of-concept for the AWS Tech U capstone. Not for real clinical use.

## Services (this monorepo)

ARIA is split into independent services that integrate through a **shared Aurora
PostgreSQL database**. Each service is owned by a team member.

| Service | Owner | Status | What it does |
|---------|-------|--------|--------------|
| `in-clinic-service/` | Marlon | ✅ Lambdas working | At-clinic AI clinical briefing + diagnostic recommendation (Bedrock + RAG) |
| `emergency-pretriage/` | Faith | _to be added_ | Emergency pre-triage: Transcribe → Comprehend → urgency routing → alerts |
| `non-emergency-pretriage/` | Felista | _to be added_ | Non-emergency pre-triage: Rekognition image analysis → Lex conversation |

Teammates: add your service as a top-level folder and link it in this table.

## How the services connect

The pre-triage services (Faith, Felista) capture the patient interaction and
write to the shared database. The In-Clinic service (Marlon) reads that data
when the patient arrives at the clinic.

**The integration contract lives in
[`in-clinic-service/INTEGRATION.md`](./in-clinic-service/INTEGRATION.md)** — it
specifies exactly which tables/columns the In-Clinic service reads, and the
shared enum values every service must use. Read it before wiring services
together.

## Shared database

All services share one Aurora Serverless v2 (PostgreSQL) database. Schema
migrations and demo/seed data for the In-Clinic portion live in
`in-clinic-service/migrations/` and `in-clinic-service/seeds/`. Coordinate
schema changes through the team so a change for one service doesn't break
another (additive, nullable columns are safest).

## Getting started

Each service has its own README and setup guide. For the In-Clinic service, see
[`in-clinic-service/README.md`](./in-clinic-service/README.md).

## Team (Group 3)

Marlon Oloo (captain) · Faith Muronji · Felista Kamau
