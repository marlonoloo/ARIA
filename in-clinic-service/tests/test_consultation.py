"""Tests for the consultation-completion handlers (finalize + send)."""
import json
from unittest import mock

from handlers import finalize_consultation, send_notification


def _event(body: dict) -> dict:
    return {"httpMethod": "POST", "body": json.dumps(body)}


# --------------------------- finalize ---------------------------

def test_finalize_requires_briefing_id():
    resp = finalize_consultation.handler(_event({"clinician_decision": "accepted"}), None)
    assert resp["statusCode"] == 400


def test_finalize_rejects_bad_decision():
    resp = finalize_consultation.handler(
        _event({"briefing_id": "b-1", "clinician_decision": "maybe"}), None
    )
    assert resp["statusCode"] == 400


def test_finalize_404_when_missing():
    with mock.patch.object(finalize_consultation, "_load_briefing_patient", return_value=None):
        resp = finalize_consultation.handler(
            _event({"briefing_id": "b-x", "clinician_decision": "accepted"}), None
        )
    assert resp["statusCode"] == 404


def test_finalize_happy_path_drafts_translated_notification():
    rec = {
        "briefing_id": "b-1", "session_id": "s-1", "patient_id": "p-1",
        "chief_complaint": "Headache", "ai_diagnosis": "Pre-eclampsia",
        "full_name": "Amara", "preferred_language": "sw",
        "email": "amara@example.com",
    }
    with mock.patch.object(finalize_consultation, "_load_briefing_patient", return_value=rec), \
         mock.patch.object(finalize_consultation, "_update_decision") as upd, \
         mock.patch.object(finalize_consultation, "_insert_prescription") as ins_rx, \
         mock.patch.object(finalize_consultation, "_insert_appointment") as ins_appt, \
         mock.patch.object(finalize_consultation, "_insert_notification") as ins_notif, \
         mock.patch.object(finalize_consultation.notifications, "translate_text",
                           return_value="<swahili>"):
        resp = finalize_consultation.handler(
            _event({
                "briefing_id": "b-1",
                "clinician_decision": "accepted",
                "prescriptions": [
                    {"drug_name": "Methyldopa", "dosage": "250mg", "frequency": "twice daily"},
                    {"dosage": "no drug name"},  # skipped
                ],
                "follow_up": {"scheduled_date": "2026-07-01", "reason": "BP review"},
            }),
            None,
        )
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["prescriptions_saved"] == 1          # the nameless one skipped
    assert body["follow_up_scheduled"] is True
    assert body["language"] == "sw"
    assert body["summary_translated"] == "<swahili>"
    upd.assert_called_once()
    ins_rx.assert_called_once()
    ins_appt.assert_called_once()
    ins_notif.assert_called_once()


def test_finalize_english_skips_translation_noop():
    rec = {
        "briefing_id": "b-1", "session_id": "s-1", "patient_id": "p-1",
        "chief_complaint": "Burn", "ai_diagnosis": "Partial-thickness burn",
        "full_name": "Grace", "preferred_language": "en", "email": "g@example.com",
    }
    with mock.patch.object(finalize_consultation, "_load_briefing_patient", return_value=rec), \
         mock.patch.object(finalize_consultation, "_update_decision"), \
         mock.patch.object(finalize_consultation, "_insert_notification"), \
         mock.patch.object(finalize_consultation.notifications, "translate_text",
                           side_effect=lambda t, l, *a, **k: t):
        resp = finalize_consultation.handler(
            _event({"briefing_id": "b-1", "clinician_decision": "accepted"}), None
        )
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["summary_en"] == body["summary_translated"]


# --------------------------- send ---------------------------

def test_send_requires_notification_id():
    resp = send_notification.handler(_event({}), None)
    assert resp["statusCode"] == 400


def test_send_404_when_missing():
    with mock.patch.object(send_notification, "_load_notification", return_value=None):
        resp = send_notification.handler(_event({"notification_id": "n-x"}), None)
    assert resp["statusCode"] == 404


def test_send_400_when_no_recipient():
    notif = {"notification_id": "n-1", "content_text": "hi", "translated_text": "hi",
             "recipient": None, "sent": False}
    with mock.patch.object(send_notification, "_load_notification", return_value=notif):
        resp = send_notification.handler(_event({"notification_id": "n-1"}), None)
    assert resp["statusCode"] == 400


def test_send_happy_path():
    notif = {"notification_id": "n-1", "content_text": "hi", "translated_text": "habari",
             "recipient": "amara@example.com", "sent": False}
    with mock.patch.object(send_notification, "_load_notification", return_value=notif), \
         mock.patch.object(send_notification.notifications, "send_email",
                           return_value="ses-msg-123") as send, \
         mock.patch.object(send_notification, "_mark_sent") as mark:
        resp = send_notification.handler(_event({"notification_id": "n-1"}), None)
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["message_id"] == "ses-msg-123"
    # Sends the stored translated text + on-file recipient when no overrides.
    send.assert_called_once()
    assert send.call_args[0][0] == "amara@example.com"
    assert send.call_args[0][2] == "habari"
    mark.assert_called_once()


def test_send_uses_overrides():
    notif = {"notification_id": "n-1", "content_text": "hi", "translated_text": "habari",
             "recipient": None, "sent": False}
    with mock.patch.object(send_notification, "_load_notification", return_value=notif), \
         mock.patch.object(send_notification.notifications, "send_email",
                           return_value="ses-msg-9") as send, \
         mock.patch.object(send_notification, "_mark_sent") as mark:
        resp = send_notification.handler(
            _event({"notification_id": "n-1", "recipient": "doc@clinic.org",
                    "content": "edited message"}),
            None,
        )
    assert resp["statusCode"] == 200
    # Override recipient + edited content are what get sent and persisted.
    assert send.call_args[0][0] == "doc@clinic.org"
    assert send.call_args[0][2] == "edited message"
    mark.assert_called_once_with("n-1", "doc@clinic.org", "edited message")


def test_send_idempotent_when_already_sent():
    notif = {"notification_id": "n-1", "content_text": "hi", "translated_text": "habari",
             "recipient": "amara@example.com", "sent": True}
    with mock.patch.object(send_notification, "_load_notification", return_value=notif), \
         mock.patch.object(send_notification.notifications, "send_email") as send:
        resp = send_notification.handler(_event({"notification_id": "n-1"}), None)
    assert resp["statusCode"] == 200
    send.assert_not_called()
