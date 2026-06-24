"""Handler tests with AWS calls mocked.

These exercise the orchestration logic (input validation, walk-in branching,
DB + Bedrock wiring) without touching real AWS services.
"""
import json
from unittest import mock

import pytest

from handlers import clinical_briefing, diagnostic_recommendation


def _event(body: dict) -> dict:
    return {"httpMethod": "POST", "body": json.dumps(body)}


# --------------------------------------------------------------------------- #
# generateClinicalBriefing
# --------------------------------------------------------------------------- #

def test_briefing_requires_patient_id():
    resp = clinical_briefing.handler(_event({}), None)
    assert resp["statusCode"] == 400


def test_briefing_404_when_patient_missing():
    with mock.patch.object(clinical_briefing, "_load_patient", return_value=None):
        resp = clinical_briefing.handler(_event({"patient_id": 99}), None)
    assert resp["statusCode"] == 404


def test_briefing_walk_in_skips_ai():
    patient = {"patient_id": "p-3", "full_name": "Grace Muthoni",
               "intake_method": "walk_in"}
    with mock.patch.object(clinical_briefing, "_load_patient", return_value=patient), \
         mock.patch.object(clinical_briefing, "_load_latest_session", return_value=None):
        resp = clinical_briefing.handler(_event({"patient_id": "p-3"}), None)
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["briefing_generated"] is False


def test_briefing_happy_path():
    patient = {"patient_id": "p-1", "full_name": "Amara",
               "intake_method": "app_triage", "gender": "female"}
    session = {"session_id": "s-10", "session_type": "emergency",
               "urgency_level": 4}
    fake_briefing = {
        "chief_complaint": "Vaginal bleeding in pregnancy",
        "ai_assessment": "Possible obstetric emergency.",
        "recommended_actions": ["Escalate to clinician", "Prepare referral"],
        "severity": "high",
    }
    with mock.patch.object(clinical_briefing, "_load_patient", return_value=patient), \
         mock.patch.object(clinical_briefing, "_load_latest_session", return_value=session), \
         mock.patch.object(clinical_briefing, "_load_conversation", return_value=[]), \
         mock.patch.object(clinical_briefing, "_load_image_findings", return_value=[]), \
         mock.patch.object(clinical_briefing.bedrock, "retrieve_protocols",
                           return_value=[{"text": "...", "score": 0.9, "source": "who"}]), \
         mock.patch.object(clinical_briefing.bedrock, "converse_json",
                           return_value=fake_briefing), \
         mock.patch.object(clinical_briefing, "_persist_briefing", return_value="b-42"):
        resp = clinical_briefing.handler(_event({"patient_id": "p-1"}), None)
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["briefing_generated"] is True
    assert body["briefing_id"] == "b-42"
    # "high" must be normalised to the DB-allowed "severe".
    assert body["briefing"]["severity"] == "severe"


# --------------------------------------------------------------------------- #
# generateDiagnosticRecommendation
# --------------------------------------------------------------------------- #

def test_diagnosis_requires_remarks():
    resp = diagnostic_recommendation.handler(_event({"briefing_id": 1}), None)
    assert resp["statusCode"] == 400


def test_diagnosis_404_when_briefing_missing():
    with mock.patch.object(diagnostic_recommendation, "_load_briefing", return_value=None):
        resp = diagnostic_recommendation.handler(
            _event({"briefing_id": "b-7", "clinician_remarks": "BP high"}), None
        )
    assert resp["statusCode"] == 404


def test_diagnosis_happy_path():
    briefing = {
        "briefing_id": "b-1", "patient_id": "p-1", "chief_complaint": "Headache in pregnancy",
        "ai_assessment": "...", "recommended_actions": "[]", "severity": "moderate",
        "full_name": "Amara", "preferred_language": "sw", "literacy_level": "low",
    }
    fake_diag = {
        "ai_diagnosis": "Pre-eclampsia suspected",
        "ai_diagnosis_actions": ["Recheck BP", "Refer urgently"],
        "severity": "high",
        "agreement_with_clinician": "aligns",
    }
    with mock.patch.object(diagnostic_recommendation, "_load_briefing", return_value=briefing), \
         mock.patch.object(diagnostic_recommendation.bedrock, "retrieve_protocols",
                           return_value=[]), \
         mock.patch.object(diagnostic_recommendation.bedrock, "converse_json",
                           return_value=fake_diag), \
         mock.patch.object(diagnostic_recommendation, "_persist_diagnosis") as persist:
        resp = diagnostic_recommendation.handler(
            _event({"briefing_id": "b-1", "clinician_remarks": "BP 150/95"}), None
        )
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["diagnosis"]["ai_diagnosis"] == "Pre-eclampsia suspected"
    persist.assert_called_once()
