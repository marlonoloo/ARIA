#!/usr/bin/env python3
"""ARIA Cognito Post-Authentication trigger.

Provisions (or links) the `patients` row on sign-in, so a patient can always
use the chat regardless of how their account was confirmed. This is the
reliable companion to the Pre-Sign-up auto-confirm trigger: auto-confirmed
users never fire Post-Confirmation, but they DO fire Post-Authentication when
they log in.

Runs synchronously during sign-in (before the token is returned) and is
idempotent via ON CONFLICT, so repeat logins are harmless.

Env:
  CLUSTER_ARN, SECRET_ARN   (required — Aurora cluster + DB credentials secret)
  DB_NAME                   (default 'postgres')
  DEFAULT_LANGUAGE          (default 'en')
"""
import os
import uuid
import boto3
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_REGION", "us-east-1")
CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DB_NAME = os.environ.get("DB_NAME", "postgres")
DEFAULT_LANGUAGE = os.environ.get("DEFAULT_LANGUAGE", "en")

rdsdata = boto3.client("rds-data", region_name=REGION)


def _param(name, value):
    if value is None:
        return {"name": name, "value": {"isNull": True}}
    return {"name": name, "value": {"stringValue": str(value)}}


def _execute(sql, params):
    return rdsdata.execute_statement(
        resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN, database=DB_NAME,
        sql=sql, parameters=[_param(k, v) for k, v in params.items()],
    )


def lambda_handler(event, context):
    attrs = (event.get("request", {}) or {}).get("userAttributes", {}) or {}
    sub = attrs.get("sub")
    phone = attrs.get("phone_number") or event.get("userName")
    language = (attrs.get("custom:preferred_language")
                or attrs.get("locale")
                or DEFAULT_LANGUAGE)
    full_name = attrs.get("name") or phone

    if not sub or not phone:
        print(f"[warn] missing sub/phone; skipping. sub={sub} phone={phone}")
        return event

    try:
        _execute(
            """INSERT INTO patients
                   (patient_id, phone_number, preferred_language, cognito_user_id,
                    full_name, intake_method, created_at, updated_at)
               VALUES (CAST(:pid AS uuid), :phone, :lang, :sub, :name,
                       'app_triage', now(), now())
               ON CONFLICT (phone_number) DO UPDATE
                   SET cognito_user_id = EXCLUDED.cognito_user_id,
                       updated_at = now()""",
            {"pid": str(uuid.uuid4()), "phone": phone, "lang": language,
             "sub": sub, "name": full_name},
        )
        print(f"[info] provisioned/linked patient for sub={sub} phone={phone}")
    except ClientError as e:
        # Never block sign-in on a DB hiccup — log for reconciliation.
        print(f"[error] patient provisioning failed for sub={sub}: {e}")

    return event
