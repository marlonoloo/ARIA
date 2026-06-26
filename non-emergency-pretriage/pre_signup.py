#!/usr/bin/env python3
"""ARIA Cognito Pre-Sign-up trigger.

Auto-confirms new patient sign-ups (and marks email/phone as verified) so a
patient can register and sign in immediately, with no confirmation code. Pair
with the Post-Confirmation trigger, which then provisions the patients row.

POC convenience only — for production you'd verify email/phone with a real code
instead of auto-confirming.

No external permissions needed: the function only mutates the event response.
Wire it as the User Pool's PreSignUp Lambda trigger.
"""


def lambda_handler(event, context):
    resp = event.setdefault("response", {})
    # Confirm the account up front so the user can log in right away.
    resp["autoConfirmUser"] = True

    attrs = (event.get("request", {}) or {}).get("userAttributes", {}) or {}
    if attrs.get("email"):
        resp["autoVerifyEmail"] = True
    if attrs.get("phone_number"):
        resp["autoVerifyPhone"] = True

    return event
