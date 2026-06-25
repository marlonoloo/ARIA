#!/usr/bin/env python3
"""ARIA Cognito Post-Confirmation trigger.

Provisions (or links) a `patients` row the moment a new patient confirms their
account, so the triage Lambda can resolve them by `cognito_user_id`. Wire this
as the User Pool's PostConfirmation Lambda trigger.

Sign-up convention (per the frontend):
  - username        = the patient's phone number (E.164, e.g. +254700000001)
  - email           = standard `email` attribute (optional in the DB)
  - preferred lang  = `custom:preferred_language` if defined, else `locale`,
                      else falls back to DEFAULT_LANGUAGE.

Talks to Aurora via the RDS Data API (no VPC / driver needed), same as the
main Lambda.

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
    # Only provision on a genuine sign-up confirmation (ignore forgot-password etc.).
    if event.get("triggerSource") != "PostConfirmation_ConfirmSignUp":
        return event

    attrs = (event.get("request", {}) or {}).get("userAttributes", {}) or {}
    sub = attrs.get("sub")
    # Username is the phone number; prefer an explicit phone_number attribute if set.
    phone = attrs.get("phone_number") or event.get("userName")
    language = (attrs.get("custom:preferred_language")
                or attrs.get("locale")
                or DEFAULT_LANGUAGE)
    # patients.full_name is NOT NULL; fall back to the name attr, then phone.
    full_name = attrs.get("name") or phone

    if not sub or not phone:
        print(f"[warn] missing sub/phone; skipping provisioning. sub={sub} phone={phone}")
        return event

    # Insert a new patient, or link an existing patient (matched by phone) to this
    # Cognito user. Never block the user's confirmation on a DB hiccup — log instead.
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
        print(f"[error] patient provisioning failed for sub={sub}: {e}")

    return event
