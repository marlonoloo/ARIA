"""Tests for the mark-briefing-reviewed (POST /briefing/reviewed) handler."""
import json
from unittest import mock

from handlers import mark_briefing_reviewed


def _event(body: dict) -> dict:
    return {"httpMethod": "POST", "body": json.dumps(body)}


def test_requires_briefing_id():
    resp = mark_briefing_reviewed.handler(_event({}), None)
    assert resp["statusCode"] == 400


def test_404_when_briefing_missing():
    with mock.patch.object(mark_briefing_reviewed, "_mark_reviewed", return_value=0):
        resp = mark_briefing_reviewed.handler(_event({"briefing_id": "b-x"}), None)
    assert resp["statusCode"] == 404


def test_marks_reviewed():
    with mock.patch.object(mark_briefing_reviewed, "_mark_reviewed", return_value=1) as m:
        resp = mark_briefing_reviewed.handler(_event({"briefing_id": "b-1"}), None)
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["reviewed"] is True
    m.assert_called_once_with("b-1", None)


def test_passes_clinician_id_when_present():
    with mock.patch.object(mark_briefing_reviewed, "_mark_reviewed", return_value=1) as m:
        mark_briefing_reviewed.handler(
            _event({"briefing_id": "b-1", "clinician_id": "c-9"}), None
        )
    m.assert_called_once_with("b-1", "c-9")
