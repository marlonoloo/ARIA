"""Patient notification helpers: Amazon Translate + Amazon SES (email).

Translate localises the consultation summary into the patient's preferred
language (a core Mothobi requirement — 70% non-native English speakers). SES
delivers it by email.

SES note: in the SES sandbox you can only send to/from *verified* identities,
so for the demo verify both the SES_SENDER address and the test recipient.
"""
from __future__ import annotations

import boto3

from shared.config import config
from shared.logging_utils import get_logger

logger = get_logger(__name__)

_translate_client = None
_ses_client = None


def _translate():
    global _translate_client
    if _translate_client is None:
        _translate_client = boto3.client("translate", region_name=config.region)
    return _translate_client


def _ses():
    global _ses_client
    if _ses_client is None:
        _ses_client = boto3.client("ses", region_name=config.region)
    return _ses_client


def translate_text(text: str, target_language: str | None, source_language: str = "en") -> str:
    """Translate text into target_language. No-op for empty text or English."""
    if not text or not target_language:
        return text
    if target_language.lower().startswith("en"):
        return text
    try:
        resp = _translate().translate_text(
            Text=text,
            SourceLanguageCode=source_language,
            TargetLanguageCode=target_language,
        )
        return resp["TranslatedText"]
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        # If translation fails, fall back to the original text rather than
        # blocking the whole consultation. Logged for visibility.
        logger.warning(
            "translate_failed",
            extra={"extra": {"target": target_language, "error": str(exc)}},
        )
        return text


def send_email(recipient: str, subject: str, body_text: str, sender: str | None = None) -> str:
    """Send a plain-text email via SES. Returns the SES MessageId."""
    resp = _ses().send_email(
        Source=sender or config.ses_sender,
        Destination={"ToAddresses": [recipient]},
        Message={
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {"Text": {"Data": body_text, "Charset": "UTF-8"}},
        },
    )
    message_id = resp["MessageId"]
    logger.info("email_sent", extra={"extra": {"message_id": message_id}})
    return message_id
