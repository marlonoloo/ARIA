"""Prompt templates for the two Bedrock calls.

Design notes (relevant to the CEDRIC "customer needs" + "well-architected"
scoring):
  - The assistant SUPPORTS a licensed clinician; it never replaces judgement.
  - Output must be grounded in the retrieved protocols; the model is told to
    say so when the protocols don't cover something rather than inventing.
  - Strict JSON output keeps the Lambda <-> database contract stable.
  - Mothobi serves many non-native English speakers, so the assistant is asked
    to interpret metaphorical/cultural symptom descriptions where relevant.
"""
from __future__ import annotations

import json
from typing import Any

CLINICAL_DISCLAIMER = (
    "This is AI-generated decision support for a licensed clinician. It is not "
    "a diagnosis and must be reviewed before any action is taken."
)

# --------------------------------------------------------------------------- #
# Clinical briefing (Lambda 1)
# --------------------------------------------------------------------------- #

BRIEFING_SYSTEM = (
    "You are ARIA, a clinical decision-support assistant for Mothobi Healthcare "
    "Group, a network of clinics across Africa. You prepare concise briefings "
    "for nurses and clinical officers BEFORE they examine a patient.\n\n"
    "Rules you must follow:\n"
    "1. You support, never replace, the clinician's judgement.\n"
    "2. Ground every clinical statement in the PROVIDED PROTOCOLS. If the "
    "protocols do not cover something, say so explicitly instead of guessing.\n"
    "3. Many patients are non-native English speakers or low-literacy. When a "
    "symptom is described metaphorically, note the plausible clinical meanings.\n"
    "4. Be concise and clinically useful. No filler.\n"
    "5. Respond with ONLY a single JSON object, no prose, no markdown."
)


def build_briefing_prompt(
    patient: dict[str, Any],
    session: dict[str, Any],
    triage_text: str,
    protocol_context: str,
) -> str:
    return (
        "Prepare a pre-examination clinical briefing.\n\n"
        f"PATIENT:\n{json.dumps(patient, indent=2, default=str)}\n\n"
        f"PRE-TRIAGE SESSION:\n{json.dumps(session, indent=2, default=str)}\n\n"
        f"PATIENT-REPORTED SYMPTOMS & PRE-TRIAGE FINDINGS:\n{triage_text}\n\n"
        f"RELEVANT CLINICAL PROTOCOLS:\n{protocol_context}\n\n"
        "Return a JSON object with exactly these fields:\n"
        "{\n"
        '  "chief_complaint": "one-line summary of the primary problem",\n'
        '  "ai_assessment": "2-4 sentence assessment grounded in the protocols",\n'
        '  "recommended_actions": ["ordered list of concrete next steps"],\n'
        '  "severity": "mild | moderate | severe | critical",\n'
        '  "protocol_sources": ["which protocols you relied on"],\n'
        '  "uncertainty_notes": "anything the protocols did not cover, or null"\n'
        "}\n"
    )


# --------------------------------------------------------------------------- #
# Diagnostic recommendation (Lambda 2)
# --------------------------------------------------------------------------- #

DIAGNOSIS_SYSTEM = (
    "You are ARIA, a clinical decision-support assistant for Mothobi Healthcare "
    "Group. A clinician has now examined the patient and recorded their own "
    "observations. Produce a diagnostic recommendation for the clinician to "
    "review, accept, modify, or reject.\n\n"
    "Rules you must follow:\n"
    "1. The clinician's examination remarks are primary evidence; weight them "
    "above the earlier pre-triage briefing.\n"
    "2. Ground recommendations in the PROVIDED PROTOCOLS. Flag any divergence "
    "between your recommendation and the clinician's remarks.\n"
    "3. If findings suggest an urgent/critical condition, say so prominently.\n"
    "4. You are decision support only; the clinician decides.\n"
    "5. Respond with ONLY a single JSON object, no prose, no markdown."
)


def build_diagnosis_prompt(
    patient: dict[str, Any],
    briefing: dict[str, Any],
    clinician_remarks: str,
    protocol_context: str,
) -> str:
    return (
        "Produce a diagnostic recommendation.\n\n"
        f"PATIENT:\n{json.dumps(patient, indent=2, default=str)}\n\n"
        f"EARLIER AI BRIEFING:\n{json.dumps(briefing, indent=2, default=str)}\n\n"
        f"CLINICIAN EXAMINATION REMARKS:\n{clinician_remarks}\n\n"
        f"RELEVANT CLINICAL PROTOCOLS:\n{protocol_context}\n\n"
        "Return a JSON object with exactly these fields:\n"
        "{\n"
        '  "ai_diagnosis": "most likely diagnosis or differential, grounded in evidence",\n'
        '  "ai_diagnosis_actions": ["ordered list of recommended clinical actions"],\n'
        '  "severity": "mild | moderate | severe | critical",\n'
        '  "agreement_with_clinician": "aligns | diverges | unclear",\n'
        '  "divergence_note": "explain any divergence from the clinician remarks, or null",\n'
        '  "protocol_sources": ["which protocols you relied on"]\n'
        "}\n"
    )
