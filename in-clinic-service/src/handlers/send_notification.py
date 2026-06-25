"""Lambda 6: sendPatientNotification.

Trigger: POST /notification/send  (doctor approves the drafted summary)

Sends the previously-drafted, translated consultation summary to the patient by
email (SES), then marks the notification approved + sent. This is the explicit
approval step: nothing reaches the patient until this is called.
"""
from __future__ import annotations

from shared import db, notifications
from shared.http import BadRequest, error, ok, parse_body
from shared.logging_utils import get_logger

logger = get_logger("sendPatientNotification")

_SUBJECT = "Your Mothobi Healthcare consultation summary"


def _load_notification(notification_id: str) -> dict | None:
    return db.query_one(
        """
        SELECT notification_id, content_text, translated_text, language,
               recipient, sent
        FROM patient_notifications
        WHERE notification_id = CAST(:nid AS uuid)
        """,
        {"nid": notification_id},
    )


def _mark_sent(notification_id: str, recipient: str, content: str):
    db.execute(
        """
        UPDATE patient_notifications
        SET approved_by_doctor = true, sent = true, sent_at = now(),
            recipient = :recipient,
            translated_text = :content
        WHERE notification_id = CAST(:nid AS uuid)
        """,
        {"nid": notification_id, "recipient": recipient, "content": content},
    )


def handler(event, context):  # noqa: ANN001
    try:
        body = parse_body(event)
        notification_id = body.get("notification_id")
        if not notification_id:
            raise BadRequest("notification_id is required")
        notification_id = str(notification_id)

        notif = _load_notification(notification_id)
        if notif is None:
            return error(404, f"Notification {notification_id} not found")

        if notif.get("sent"):
            # Idempotent: don't double-send.
            return ok({"notification_id": notification_id, "sent": True,
                       "note": "Already sent."})

        # Optional doctor overrides made during review.
        override_recipient = (body.get("recipient") or "").strip() or None
        override_content = body.get("content")

        recipient = override_recipient or notif.get("recipient")
        if not recipient:
            return error(400, "No recipient email provided or on file")

        body_text = (
            override_content
            if (override_content and override_content.strip())
            else (notif.get("translated_text") or notif.get("content_text"))
        )
        message_id = notifications.send_email(recipient, _SUBJECT, body_text)

        # Persist the final recipient + (possibly edited) text for the audit trail.
        _mark_sent(notification_id, recipient, body_text)

        return ok(
            {
                "notification_id": notification_id,
                "sent": True,
                "recipient": recipient,
                "message_id": message_id,
            }
        )

    except BadRequest as exc:
        return error(400, str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("send_notification_failed")
        return error(500, f"Failed to send notification: {exc}")
