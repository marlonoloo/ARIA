"""Tests for the patient dashboard (GET /patients) handler."""
import json
from unittest import mock

from handlers import patient_dashboard


def test_dashboard_returns_rows():
    rows = [
        {"briefing_id": "b-1", "patient_id": "p-1", "patient_name": "Amara",
         "urgency_level": 4, "severity": "critical"},
        {"briefing_id": "b-2", "patient_id": "p-2", "patient_name": "Juma",
         "urgency_level": 2, "severity": "moderate"},
    ]
    with mock.patch.object(patient_dashboard, "_load_dashboard", return_value=rows) as load:
        resp = patient_dashboard.handler({"queryStringParameters": None}, None)
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["count"] == 2
    assert body["patients"][0]["patient_name"] == "Amara"
    load.assert_called_once_with(None)


def test_dashboard_clinic_filter():
    with mock.patch.object(patient_dashboard, "_load_dashboard", return_value=[]) as load:
        resp = patient_dashboard.handler(
            {"queryStringParameters": {"clinic_id": "c-123"}}, None
        )
    assert resp["statusCode"] == 200
    load.assert_called_once_with("c-123")


def test_dashboard_handles_db_error():
    with mock.patch.object(patient_dashboard, "_load_dashboard",
                           side_effect=RuntimeError("boom")):
        resp = patient_dashboard.handler({"queryStringParameters": None}, None)
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 500
    assert "error" in body
