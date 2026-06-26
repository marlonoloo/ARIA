# Project ARIA — System Architecture

Whole-system view of ARIA (Accessible Real-time Intelligent Assistant) for
Mothobi Healthcare Group. Three services integrate through one shared Aurora
database. This is the reference for the architecture diagram and pitch.

> AWS Tech U capstone (Group 3). Proof-of-concept — not for real clinical use.

---

## Services by owner

| Service | Owner | Gateway | Purpose |
|---------|-------|---------|---------|
| **Emergency Triage** | Felista | HTTP API | Voice-first emergency intake → severity → alert + briefing |
| **Non-Emergency Consultation** | Faith | HTTP API | Authenticated chat/voice/image triage → routing + briefing |
| **In-Clinic Service** | Marlon | HTTP API | Doctor dashboard: briefing → diagnosis → prescription → patient email |

All gateways are HTTP APIs. (Multiple gateway IDs exist; treat as one logical
API layer with a Cognito JWT authorizer.)

---

## System diagram (Mermaid)

```mermaid
flowchart TB
    subgraph FE["Frontend — S3 + CloudFront"]
        IDX["index.html"]
        EMG_UI["emergency.html + app.js<br/>(voice, no login)"]
        CHAT_UI["chat.html<br/>(non-emergency)"]
        PLOGIN["patient-login.html"]
        DLOGIN["doctor-login.html"]
        DOC_UI["doctor.html + doctor.js"]
    end

    subgraph COG["Amazon Cognito"]
        UP["User Pool (patients + doctors)<br/>role via patients/clinicians tables"]
        IP["Identity Pool<br/>(browser Polly creds)"]
    end

    APIGW["API Gateway (HTTP APIs)<br/>JWT authorizer (User Pool)"]

    subgraph EMERG["Emergency Triage (Felista)"]
        L_AUDIO["ARIA_AudioProcessor"]
        L_FULFILL["ARIA_EmergencyFulfillment"]
        LEX["Amazon Lex V2"]
    end

    subgraph NONEMERG["Non-Emergency (Faith)"]
        L_TRIAGE["aria-triage (chat_functionality)"]
        L_VOICE["aria-voice (async, S3 event)"]
        NEAREST["/nearest-clinic (public)"]
    end

    subgraph INCLINIC["In-Clinic (Marlon)"]
        L_DASH["patientDashboard"]
        L_BRIEF["generateClinicalBriefing"]
        L_DIAG["generateDiagnosticRecommendation"]
        L_FIN["finalizeConsultation"]
        L_SEND["sendPatientNotification"]
        L_REV["markBriefingReviewed"]
    end

    subgraph AI["Shared AI/ML"]
        TRANSCRIBE["Transcribe"]
        TRANSLATE["Translate"]
        COMPREHEND["Comprehend (+ Medical)"]
        REKOG["Rekognition"]
        POLLY["Polly"]
        BEDROCK["Bedrock — Claude"]
        KB["Bedrock Knowledge Base (RAG)"]
    end

    subgraph DATA["Shared Data"]
        AUR[("Aurora Serverless v2<br/>PostgreSQL — RDS Data API")]
        SM["Secrets Manager"]
        S3["S3 (media + KB docs + hosting)"]
        SNS["SNS (clinic alerts)"]
        SES["SES (patient email)"]
    end

    PLOGIN & DLOGIN --> UP
    EMG_UI -. guest creds .-> IP --> POLLY
    DOC_UI --> APIGW
    CHAT_UI --> APIGW
    EMG_UI --> APIGW
    APIGW -. validates JWT .- UP

    APIGW --> L_AUDIO --> TRANSCRIBE & TRANSLATE & LEX
    LEX --> L_FULFILL
    L_FULFILL --> COMPREHEND & SNS & TRANSLATE
    L_FULFILL -->|POST /briefing| L_BRIEF

    APIGW --> L_TRIAGE
    L_TRIAGE --> TRANSCRIBE & TRANSLATE & COMPREHEND & REKOG & BEDROCK & POLLY
    L_TRIAGE -->|writes briefing directly| AUR
    NEAREST --> AUR
    L_VOICE --> TRANSCRIBE

    APIGW --> L_DASH & L_BRIEF & L_DIAG & L_FIN & L_SEND & L_REV
    L_BRIEF & L_DIAG --> KB
    L_BRIEF & L_DIAG --> BEDROCK
    L_FIN --> TRANSLATE
    L_SEND --> SES

    L_AUDIO & L_FULFILL & L_TRIAGE & L_DASH & L_BRIEF & L_DIAG & L_FIN & L_SEND & L_REV --> AUR
    AUR -. creds .- SM
    KB -. embeddings .- S3
```

---

## Integration facts (keep the diagram honest)

- **`clinical_briefings` has two writers:**
  - Non-emergency (Faith) writes the briefing **directly** (its own Bedrock call) at escalation / one-shot triage.
  - Emergency (Felista) calls the in-clinic **`POST /briefing`** (RAG-grounded).
  - The doctor can **regenerate** a KB-grounded briefing on demand via `POST /briefing`.
  - All paths set `viewed_by_clinician = false`, so every briefing appears in the doctor queue.
- **The doctor dashboard is the single sink** for briefings from all triage paths.
- **One Cognito User Pool** (`us-east-1_7EcteStu9`, client `2naufa434t15vjrrl7aru34fqr`) for **both** patients and doctors. The distinction is role/provisioning — `patients.cognito_user_id` vs `clinicians.cognito_user_id` — resolved via `/clinician/whoami`. A separate **Identity Pool** provides browser Polly credentials for the (unauthenticated) emergency page.
- **One shared Aurora DB** is the integration hub: every Lambda reads/writes it via the RDS Data API; credentials in Secrets Manager. Schema changes are additive/coordinated.
- **`/nearest-clinic`** is a single public endpoint (Faith) consumed by both the non-emergency and the anonymous emergency pages.
- **Tables:** `notifications` (clinic-facing alerts) and `patient_notifications` (in-clinic patient email) are distinct — no collision.
- **RAG / Knowledge Base** is specific to the in-clinic briefing/diagnosis. Non-emergency uses Bedrock (Claude + vision) without the KB.
- **In-clinic `/briefing` will add Comprehend Medical** for entity extraction feeding retrieval (planned).

---

## AWS services (system-wide)

S3, CloudFront, API Gateway (HTTP API), AWS Lambda, Amazon Cognito (User Pool +
Identity Pool), Amazon Lex V2, Amazon Transcribe, Amazon Translate, Amazon
Comprehend (+ Comprehend Medical), Amazon Rekognition, Amazon Polly, Amazon
Bedrock (Claude), Bedrock Knowledge Bases (RAG), Aurora Serverless v2
(PostgreSQL, RDS Data API), Secrets Manager, Amazon SNS, Amazon SES, IAM,
CloudWatch.

---

## Key cross-cutting trade-offs

- **Shared relational DB (Aurora) over per-service stores** — clean integration and referential integrity across patients/sessions/messages/briefings; cost is coordinated schema changes (kept additive).
- **RAG over fine-tuning** (in-clinic) — auditable, instantly updatable clinical grounding.
- **Human-in-the-loop** — AI is decision-support; the clinician accepts/modifies/rejects and must approve before any patient notification is sent.
- **Multiple API gateways** — convenient per-owner, but CORS/authorizers must be configured per gateway (a missed CORS config surfaced only in the browser).
- **Known limitations (future work):** prescribing is doctor-entered (no AI drug selection, no allergy/interaction checking); SES/SMS in sandbox; sentiment→severity in emergency is a crude proxy for clinical acuity.
