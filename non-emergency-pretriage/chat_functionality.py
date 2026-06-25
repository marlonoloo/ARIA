#!/usr/bin/env python3
"""Project ARIA - triage Lambda.
One-shot triage + voice (S3/Transcribe) + conversational /chat with Claude vision
+ optional Polly speech output (phonetic voice for Swahili/Zulu).
Backed by Aurora via the RDS Data API (no VPC, no psycopg2)."""

import os
import json
import time
import uuid
import urllib.parse
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = os.environ["BEDROCK_MODEL_ID"]
CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DB_NAME = os.environ.get("DB_NAME", "postgres")
API_KEY = os.environ.get("API_KEY")
MEDIA_BUCKET = os.environ.get("MEDIA_BUCKET", "aria-voice-325058823230-use1")

DETECT_CONFIDENCE_THRESHOLD = 0.70

RED_FLAGS = {
    "not breathing", "can't breathe", "cannot breathe", "difficulty breathing",
    "collapsed", "unconscious", "unresponsive", "fainted", "passed out",
    "chest pain", "severe bleeding", "heavy bleeding", "seizure", "convulsion",
    "choking", "stroke", "blue lips", "no pulse",
}

RED_FLAGS_NATIVE = {
    "sw": {
        "hapumui", "hawezi kupumua", "shida ya kupumua", "ugumu wa kupumua",
        "amezimia", "kuzimia", "amepoteza fahamu", "hana fahamu", "kupoteza fahamu",
        "kifafa", "degedege", "damu nyingi", "anatokwa damu nyingi",
        "maumivu makali ya kifua", "kifua kinauma sana", "anasongwa", "kiharusi",
    },
}

# Proper Polly voice per language; sw/zu have no Polly voice, so they fall back to
# a Spanish neural voice that reads Swahili text with roughly correct phonetics.
POLLY_VOICES = {"en": "Joanna", "fr": "Lea", "es": "Lupe", "pt": "Vitoria", "ar": "Hala"}
PHONETIC_FALLBACK = "Lupe"

translate = boto3.client("translate", region_name=REGION)
comprehend = boto3.client("comprehend", region_name=REGION)
comprehend_med = boto3.client("comprehendmedical", region_name=REGION)
bedrock = boto3.client("bedrock-runtime", region_name=REGION)
rdsdata = boto3.client("rds-data", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION, config=Config(signature_version="s3v4"))
transcribe = boto3.client("transcribe", region_name=REGION)
rekognition = boto3.client("rekognition", region_name=REGION)
polly = boto3.client("polly", region_name=REGION)


# ---------------- Data API helpers ----------------
def _rds(method, **kwargs):
    for attempt in range(6):
        try:
            return getattr(rdsdata, method)(**kwargs)
        except ClientError as e:
            if (e.response.get("Error", {}).get("Code") == "DatabaseResumingException"
                    and attempt < 5):
                print(f"[info] DB resuming, retry {attempt + 1}")
                time.sleep(3)
                continue
            raise


def _param(name, value):
    if value is None:
        return {"name": name, "value": {"isNull": True}}
    if isinstance(value, bool):
        return {"name": name, "value": {"booleanValue": value}}
    if isinstance(value, int):
        return {"name": name, "value": {"longValue": value}}
    if isinstance(value, float):
        return {"name": name, "value": {"doubleValue": value}}
    return {"name": name, "value": {"stringValue": str(value)}}


def execute(sql, params=None, tx=None):
    kwargs = {
        "resourceArn": CLUSTER_ARN, "secretArn": SECRET_ARN, "database": DB_NAME,
        "sql": sql,
        "parameters": [_param(k, v) for k, v in (params or {}).items()],
    }
    if tx:
        kwargs["transactionId"] = tx
    return _rds("execute_statement", **kwargs)


def get_patient(phone):
    r = execute("SELECT patient_id::text, clinic_id::text, preferred_language, "
                "COALESCE(prefers_voice, true) FROM patients WHERE phone_number = :phone",
                {"phone": phone})
    recs = r.get("records", [])
    if not recs:
        raise ValueError(f"No patient with phone {phone}")
    row = recs[0]
    return (row[0].get("stringValue"), row[1].get("stringValue"),
            row[2].get("stringValue"), row[3].get("booleanValue", True))

def patient_phone_from_sub(sub):
    r = execute("SELECT phone_number FROM patients WHERE cognito_user_id = :sub", {"sub": sub})
    recs = r.get("records", [])
    return recs[0][0].get("stringValue") if recs else None


# ---------------- Voice / Image / Speech helpers ----------------
def transcribe_s3(bucket, key):
    job = f"aria-{uuid.uuid4()}"
    out_key = f"transcripts/{job}.json"
    params = {
        "TranscriptionJobName": job,
        "Media": {"MediaFileUri": f"s3://{bucket}/{key}"},
        "OutputBucketName": bucket, "OutputKey": out_key,
        "IdentifyLanguage": True,
    }
    fmt = key.rsplit(".", 1)[-1].lower()
    if fmt in {"mp3", "mp4", "wav", "flac", "ogg", "amr", "webm", "m4a"}:
        params["MediaFormat"] = "mp4" if fmt == "m4a" else fmt
    transcribe.start_transcription_job(**params)
    while True:
        r = transcribe.get_transcription_job(TranscriptionJobName=job)
        st = r["TranscriptionJob"]["TranscriptionJobStatus"]
        if st in ("COMPLETED", "FAILED"):
            break
        time.sleep(4)
    if st == "FAILED":
        raise RuntimeError(r["TranscriptionJob"].get("FailureReason", "transcribe failed"))
    obj = s3.get_object(Bucket=bucket, Key=out_key)
    data = json.loads(obj["Body"].read())
    return data["results"]["transcripts"][0]["transcript"], r["TranscriptionJob"].get("LanguageCode")


def analyze_image(bucket, key):
    r = rekognition.detect_labels(
        Image={"S3Object": {"Bucket": bucket, "Name": key}},
        MaxLabels=15, MinConfidence=60)
    labels = [(l["Name"], round(l["Confidence"], 1)) for l in r.get("Labels", [])]
    summary = ", ".join(f"{n} {c}%" for n, c in labels) or "no clear labels"
    top_name = labels[0][0] if labels else None
    top_conf = (labels[0][1] / 100.0) if labels else None
    return labels, summary, top_name, top_conf


def _image_block(bucket, key):
    data = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    ext = key.rsplit(".", 1)[-1].lower()
    fmt = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png",
           "gif": "gif", "webp": "webp"}.get(ext, "jpeg")
    return {"image": {"format": fmt, "source": {"bytes": data}}}


def synthesize_to_s3(text, lang, bucket, session_id):
    voice = POLLY_VOICES.get(lang, PHONETIC_FALLBACK)
    r = polly.synthesize_speech(Text=text[:2900], OutputFormat="mp3",
                                VoiceId=voice, Engine="neural")
    key = f"audio-out/{session_id}-{uuid.uuid4().hex[:8]}.mp3"
    s3.put_object(Bucket=bucket, Key=key, Body=r["AudioStream"].read(),
                  ContentType="audio/mpeg")
    url = s3.generate_presigned_url("get_object",
                                    Params={"Bucket": bucket, "Key": key},
                                    ExpiresIn=3600)
    return url, voice


# ---------------- Language helpers ----------------
def detect_language(text, profile_lang):
    detected, score = None, 0.0
    try:
        r = comprehend.detect_dominant_language(Text=text)
        langs = r.get("Languages", [])
        if langs:
            top = max(langs, key=lambda x: x["Score"])
            detected, score = top["LanguageCode"], float(top["Score"])
    except Exception as ex:
        print(f"[warn] language detection skipped: {ex}")
    if detected and score >= DETECT_CONFIDENCE_THRESHOLD:
        return detected, detected, score
    return (profile_lang or "auto"), detected, score


def to_english(text, source_lang=None):
    if source_lang == "en":
        return text, "en"
    r = translate.translate_text(Text=text, SourceLanguageCode=source_lang or "auto",
                                 TargetLanguageCode="en")
    return r["TranslatedText"], r["SourceLanguageCode"]


def from_english(text, target_lang):
    if not text or target_lang == "en":
        return text
    r = translate.translate_text(Text=text, SourceLanguageCode="en",
                                 TargetLanguageCode=target_lang)
    return r["TranslatedText"]


def find_red_flag(text, lang="en"):
    t = (text or "").lower()
    terms = RED_FLAGS if lang == "en" else RED_FLAGS_NATIVE.get(lang, set())
    for flag in terms:
        if flag in t:
            return flag
    return None


# ---------------- Medical / AI helpers ----------------
def extract_entities(english_text):
    try:
        r = comprehend_med.detect_entities_v2(Text=english_text)
        out = {}
        for e in r.get("Entities", []):
            out.setdefault(e["Category"], []).append(e["Text"])
        return out
    except Exception as ex:
        print(f"[warn] Comprehend Medical skipped: {ex}")
        return {}


SYSTEM_PROMPT = """You are ARIA, a clinical triage assistant for a healthcare group.
You are NOT a doctor; your output must be reviewed by a clinician.
Given a patient's symptoms (already in English) and extracted medical entities,
produce a concise triage briefing.

Respond with ONLY a valid JSON object (no markdown, no commentary) with keys:
  "chief_complaint": one-sentence summary,
  "ai_assessment": brief clinical reasoning,
  "severity": one of "mild","moderate","severe","critical",
  "urgency_level": integer 1-5 (5 = most urgent),
  "recommended_actions": what the clinician should consider,
  "first_aid_given": simple, safe guidance to give the patient now,
  "needs_in_person": true or false
"""


def generate_briefing(english_text, entities):
    user_msg = (f"Patient says: {english_text}\n\n"
                f"Extracted entities: {json.dumps(entities)}")
    r = bedrock.converse(
        modelId=MODEL_ID, system=[{"text": SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": user_msg}]}],
        inferenceConfig={"maxTokens": 800, "temperature": 0.2},
    )
    text = r["output"]["message"]["content"][0]["text"].strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):text.rfind("}") + 1]
    return json.loads(text)


# ---------------- Conversational chatbot ----------------
CHAT_SYSTEM_PROMPT = """You are ARIA, a friendly clinical triage assistant for a
healthcare group. You chat with patients to understand symptoms, give simple safe
first-aid guidance, and decide whether they need to visit a clinic. You are NOT a
doctor and must never give a definitive diagnosis.

Rules:
- Ask ONE short, clear follow-up question at a time. Keep language simple.
- Do NOT repeat a question the patient has already answered; if an answer is unclear,
  briefly acknowledge it and move on.
- Offer simple, safe self-care/first-aid tips when appropriate.
- Route the patient to a clinic if symptoms are severe, have persisted several days
  without improving, are worsening, or clearly need in-person care.
- When you route to a clinic, set "recommended_service" to the most relevant of:
  general, burns, maternity, pediatrics.
- If a photo is included, look at it carefully. Describe objectively what you SEE in
  "image_findings" (location, redness, swelling, wound, rash). This is an observation
  to help a clinician, NOT a diagnosis. Use it to inform your reply.
- Always write in English; it will be translated for the patient.

Respond with ONLY a JSON object:
{
  "reply": "<what to say to the patient: a question or advice>",
  "action": "continue" | "advise" | "route_to_clinic",
  "image_findings": "<objective visual description if a photo was shared, else null>",
  "recommended_service": "<general|burns|maternity|pediatrics; if route_to_clinic>",
  "chief_complaint": "<short summary; required if route_to_clinic>",
  "ai_assessment": "<brief clinical reasoning; if route_to_clinic>",
  "severity": "mild|moderate|severe|critical (if route_to_clinic)",
  "urgency_level": <integer 1-5; if route_to_clinic>,
  "recommended_actions": "<for the clinician; if route_to_clinic>",
  "first_aid_given": "<summary of advice given; if route_to_clinic>"
}
"""


def _next_seq(session_id):
    r = execute("SELECT COALESCE(MAX(sequence_order),0)+1 AS n FROM messages "
                "WHERE session_id=CAST(:sid AS uuid)", {"sid": session_id})
    return int(r["records"][0][0]["longValue"])


def load_history(session_id):
    r = execute("SELECT sender, translated_text FROM messages "
                "WHERE session_id=CAST(:sid AS uuid) ORDER BY sequence_order",
                {"sid": session_id})
    msgs = []
    for row in r.get("records", []):
        sender = row[0].get("stringValue")
        text = row[1].get("stringValue") or ""
        msgs.append({"role": "user" if sender == "patient" else "assistant",
                     "content": [{"text": text}]})
    return msgs


def save_message(session_id, sender, original, english, lang, seq):
    execute("""INSERT INTO messages (session_id, sender, original_text,
                   translated_text, detected_language, input_type, sequence_order)
               VALUES (CAST(:sid AS uuid), :sender, :orig, :trans, :lang, 'text', :seq)""",
            {"sid": session_id, "sender": sender, "orig": original,
             "trans": english, "lang": lang, "seq": seq})

def nearest_clinic(lat, lng, service=None):
    where = "is_active = true AND latitude IS NOT NULL AND longitude IS NOT NULL"
    params = {"lat": float(lat), "lng": float(lng)}
    if service:
        where += " AND :svc = ANY(services_available)"
        params["svc"] = service
    sql = f"""SELECT clinic_id::text, clinic_name, location,
                (6371 * acos(LEAST(1, GREATEST(-1,
                   cos(radians(:lat)) * cos(radians(latitude)) *
                   cos(radians(longitude) - radians(:lng)) +
                   sin(radians(:lat)) * sin(radians(latitude)))))) AS dist
              FROM clinics WHERE {where} ORDER BY dist ASC LIMIT 1"""
    r = execute(sql, params)
    recs = r.get("records", [])
    if not recs and service:          # nothing with that service -> nearest of any
        return nearest_clinic(lat, lng)
    if not recs:
        return None
    row = recs[0]
    return {"clinic_id": row[0].get("stringValue"), "name": row[1].get("stringValue"),
            "location": row[2].get("stringValue"),
            "distance_km": round(row[3].get("doubleValue", 0.0), 1)}


def chat_turn(phone, message, session_id=None, image_key=None, audio_key=None, bucket=None, speak=None, lat=None, lng=None):
    patient_id, clinic_id, patient_lang, prefers_voice = get_patient(phone)
    patient_lang = patient_lang or "en"
    bucket = bucket or MEDIA_BUCKET
    if speak is None:
        speak = prefers_voice
    if audio_key and not message:
        message, _ = transcribe_s3(bucket, audio_key)

    english, src_lang = "", patient_lang
    if message:
        src_lang, _, _ = detect_language(message, patient_lang)
        try:
            english, src_lang = to_english(message, source_lang=src_lang)
        except Exception:
            english, src_lang = to_english(message, source_lang=None)

    if not session_id:
        session_id = execute(
            "INSERT INTO sessions (patient_id, session_type, status, assigned_clinic_id) "
            "VALUES (CAST(:pid AS uuid), 'non_emergency', 'active', CAST(:clinic AS uuid)) "
            "RETURNING session_id::text",
            {"pid": patient_id, "clinic": clinic_id})["records"][0][0]["stringValue"]

    seq = _next_seq(session_id)
    red_flag = find_red_flag(english) or find_red_flag(message, lang=patient_lang)

    if red_flag:
        reply_en = ("This may be a medical emergency. I am alerting a clinic now. "
                    "If the person has stopped breathing or is unresponsive, call "
                    "emergency services immediately.")
        decision = {"action": "route_to_clinic",
                    "chief_complaint": english or "Emergency reported",
                    "ai_assessment": f"Red-flag symptom detected: {red_flag}.",
                    "severity": "critical", "urgency_level": 5,
                    "recommended_actions": "Immediate clinical assessment / emergency response.",
                    "first_aid_given": reply_en, "image_findings": None}
    else:
        history = load_history(session_id)
        turn_text = english or "Please look at the photo I am sharing."
        if message and message != english:
            turn_text += f"\n\n(Patient's original words: {message})"
        user_content = [{"text": turn_text}]

        if image_key:
            user_content.append(_image_block(bucket, image_key))
        history.append({"role": "user", "content": user_content})
        resp = bedrock.converse(modelId=MODEL_ID, system=[{"text": CHAT_SYSTEM_PROMPT}],
                                messages=history,
                                inferenceConfig={"maxTokens": 800, "temperature": 0.3})
        raw = resp["output"]["message"]["content"][0]["text"].strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw[raw.find("{"):raw.rfind("}") + 1]
        decision = json.loads(raw)
        reply_en = decision.get("reply", "Could you tell me a bit more about how you feel?")

    img_findings = decision.get("image_findings")

    # Decide routing + nearest clinic BEFORE composing the reply, so the clinic
    # name lands in the translated/spoken reply too.
    action = decision.get("action", "continue")
    escalated = action == "route_to_clinic"
    nearest = None
    routed_clinic = clinic_id
    if escalated and lat is not None and lng is not None:
        nearest = nearest_clinic(lat, lng, decision.get("recommended_service"))
        if nearest:
            routed_clinic = nearest["clinic_id"]
            reply_en += (f" Please go to {nearest['name']} in {nearest['location']}, "
                         f"about {nearest['distance_km']} km away.")

    stored_text = english
    if image_key:
        stored_text = (english + f" [Photo shared. Visual findings: {img_findings}]").strip()
    save_message(session_id, "patient", message or "[photo shared]",
                 stored_text or "[photo shared]", src_lang, seq)

    reply_patient = from_english(reply_en, patient_lang)
    save_message(session_id, "aria", reply_patient, reply_en, patient_lang, seq + 1)

    audio_url = None
    if speak:
        try:
            audio_url, _ = synthesize_to_s3(reply_patient, patient_lang, bucket, session_id)
        except Exception as ex:
            print(f"[warn] polly skipped: {ex}")

    if image_key:
        try:
            labels, _, top_name, top_conf = analyze_image(bucket, image_key)
        except Exception as ex:
            print(f"[warn] rekognition skipped: {ex}")
            labels, top_name, top_conf = [], None, None
        execute("""INSERT INTO image_analyses (session_id, s3_uri, rekognition_labels,
                       custom_labels, detected_condition, confidence_score)
                   VALUES (CAST(:sid AS uuid), :uri, CAST(:rek AS jsonb),
                           CAST(:claude AS jsonb), :cond, :conf)""",
                {"sid": session_id, "uri": f"s3://{bucket}/{image_key}",
                 "rek": json.dumps([{"name": n, "confidence": c} for n, c in labels]),
                 "claude": json.dumps({"findings": img_findings}),
                 "cond": top_name, "conf": top_conf})

    if escalated:
        is_emerg = decision.get("severity") == "critical" or bool(red_flag)
        execute("""UPDATE sessions SET status='escalated', session_type=:st,
                       urgency_level=:urg, assigned_clinic_id=CAST(:clinic AS uuid),
                       briefing_generated=true, ended_at=NOW()
                   WHERE session_id=CAST(:sid AS uuid)""",
                {"st": "emergency" if is_emerg else "non_emergency",
                 "urg": decision.get("urgency_level"), "clinic": routed_clinic,
                 "sid": session_id})
        execute("""INSERT INTO clinical_briefings (session_id, patient_id,
                       processing_status, chief_complaint, ai_assessment, severity,
                       recommended_actions, first_aid_given, needs_in_person)
                   VALUES (CAST(:sid AS uuid), CAST(:pid AS uuid), 'complete', :cc,
                           :assess, :sev, :ra, :aid, true)
                   ON CONFLICT (session_id) DO NOTHING""",
                {"sid": session_id, "pid": patient_id,
                 "cc": decision.get("chief_complaint", english or "Photo-based concern"),
                 "assess": decision.get("ai_assessment"), "sev": decision.get("severity"),
                 "ra": decision.get("recommended_actions"),
                 "aid": decision.get("first_aid_given")})
        execute("""INSERT INTO notifications (session_id, clinic_id, notification_type)
                   VALUES (CAST(:sid AS uuid), CAST(:clinic AS uuid), :nt)""",
                {"sid": session_id, "clinic": routed_clinic,
                 "nt": "emergency_alert" if is_emerg else "patient_arriving"})

    return {"session_id": session_id, "reply": reply_patient, "reply_english": reply_en,
            "action": action, "escalated": escalated,
            "image_analyzed": bool(image_key), "image_findings": img_findings,
            "audio_url": audio_url, "patient_text": message,
            "clinic": nearest, "language": patient_lang}

# ---------------- One-shot triage ----------------
def run_triage(message, phone, emergency=False, input_type="text", audio_s3_uri=None):
    patient_id, clinic_id, patient_lang, _ = get_patient(phone)
    patient_lang = patient_lang or "en"

    src_lang, detected, score = detect_language(message, patient_lang)
    try:
        english, src_lang = to_english(message, source_lang=src_lang)
    except Exception:
        english, src_lang = to_english(message, source_lang=None)

    red_flag = find_red_flag(english) or find_red_flag(message, lang=patient_lang)
    auto_escalated = bool(red_flag) and not emergency
    is_emergency = emergency or bool(red_flag)
    session_type = "emergency" if is_emergency else "non_emergency"

    entities, briefing = None, None
    if not is_emergency:
        entities = extract_entities(english)
        briefing = generate_briefing(english, entities)

    tx = _rds("begin_transaction", resourceArn=CLUSTER_ARN,
              secretArn=SECRET_ARN, database=DB_NAME)["transactionId"]
    try:
        sid = execute(
            """INSERT INTO sessions (patient_id, session_type, status,
                   urgency_level, assigned_clinic_id)
               VALUES (CAST(:pid AS uuid), :stype, :status, :urg, CAST(:clinic AS uuid))
               RETURNING session_id::text""",
            {"pid": patient_id, "stype": session_type,
             "status": "escalated" if is_emergency else "active",
             "urg": 5 if is_emergency else None, "clinic": clinic_id}, tx
        )["records"][0][0]["stringValue"]

        execute(
            """INSERT INTO messages (session_id, sender, original_text, translated_text,
                   detected_language, input_type, audio_s3_uri,
                   comprehend_entities, sequence_order)
               VALUES (CAST(:sid AS uuid), 'patient', :orig, :trans, :lang, :itype,
                       :audio, CAST(:entities AS jsonb), 1)""",
            {"sid": sid, "orig": message, "trans": english, "lang": src_lang,
             "itype": input_type, "audio": audio_s3_uri,
             "entities": json.dumps(entities or {})}, tx)

        result = {
            "session_id": sid, "session_type": session_type,
            "escalated": is_emergency, "auto_escalated": auto_escalated,
            "red_flag": red_flag, "source_language": src_lang,
            "patient_language": patient_lang, "english": english,
            "input_type": input_type, "briefing": None, "patient_guidance": None,
        }

        if is_emergency:
            execute(
                """INSERT INTO clinical_briefings (session_id, patient_id,
                       processing_status, chief_complaint, patient_context,
                       needs_in_person, flagged_for_review)
                   VALUES (CAST(:sid AS uuid), CAST(:pid AS uuid), 'raw', :cc, :ctx, true, true)""",
                {"sid": sid, "pid": patient_id, "cc": english, "ctx": english}, tx)
            execute("UPDATE sessions SET briefing_generated=true "
                    "WHERE session_id=CAST(:sid AS uuid)", {"sid": sid}, tx)
        else:
            b = briefing
            execute(
                """INSERT INTO clinical_briefings (session_id, patient_id,
                       processing_status, chief_complaint, ai_assessment, severity,
                       recommended_actions, first_aid_given, needs_in_person)
                   VALUES (CAST(:sid AS uuid), CAST(:pid AS uuid), 'complete', :cc,
                           :assess, :sev, :actions, :aid, :inperson)""",
                {"sid": sid, "pid": patient_id, "cc": b["chief_complaint"],
                 "assess": b["ai_assessment"], "sev": b["severity"],
                 "actions": b["recommended_actions"], "aid": b.get("first_aid_given"),
                 "inperson": bool(b.get("needs_in_person", True))}, tx)
            execute("""UPDATE sessions SET status='completed', urgency_level=:urg,
                       briefing_generated=true, ended_at=NOW()
                       WHERE session_id=CAST(:sid AS uuid)""",
                    {"urg": b.get("urgency_level"), "sid": sid}, tx)

        _rds("commit_transaction", resourceArn=CLUSTER_ARN,
             secretArn=SECRET_ARN, transactionId=tx)
    except Exception:
        try:
            rdsdata.rollback_transaction(resourceArn=CLUSTER_ARN,
                                         secretArn=SECRET_ARN, transactionId=tx)
        except Exception:
            pass
        raise

    if not is_emergency:
        result["briefing"] = briefing
        result["patient_guidance"] = from_english(briefing.get("first_aid_given", ""),
                                                  patient_lang)
    return result


# ---------------- Handlers ----------------
def _resp(code, body):
    return {"statusCode": code,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body, default=str)}


def lambda_handler(event, context):
    try:
        method = (event.get("requestContext", {}).get("http", {}) or {}).get("method", "")
        if method == "OPTIONS":
            return _resp(200, {"ok": True})

        path = event.get("rawPath") or event.get("path") or "/"
        claims = (event.get("requestContext", {}).get("authorizer", {})
                  .get("jwt", {}).get("claims", {})) or {}

        if path.endswith("/clinician/whoami"):
            sub = claims.get("sub")
            r = execute("SELECT clinician_id::text, full_name, role FROM clinicians "
                        "WHERE cognito_user_id = :sub", {"sub": sub})
            recs = r.get("records", [])
            if not recs:
                return _resp(403, {"error": "clinician not provisioned", "sub": sub})
            row = recs[0]
            return _resp(200, {"clinician_id": row[0].get("stringValue"),
                               "full_name": row[1].get("stringValue"),
                               "role": row[2].get("stringValue"),
                               "username": claims.get("cognito:username") or claims.get("email")})

        body = event.get("body") or "{}"
        if isinstance(body, str):
            body = json.loads(body)

        # Public clinic locator — no patient/auth needed, so the (anonymous)
        # emergency flow can find the nearest clinic from coordinates.
        # Body: { "lat": <num>, "lng": <num>, "service": <optional> }
        if path.endswith("/nearest-clinic"):
            lat = body.get("lat")
            lng = body.get("lng")
            if lat is None or lng is None:
                return _resp(400, {"error": "lat and lng are required"})
            try:
                clinic = nearest_clinic(lat, lng, body.get("service"))
            except Exception as e:
                print(f"[error] nearest-clinic lookup failed: {e}")
                return _resp(500, {"error": "clinic lookup failed"})
            if not clinic:
                return _resp(404, {"error": "no active clinics found"})
            return _resp(200, {"clinic": clinic})

        if claims:                       # JWT-authenticated patient route
            phone = patient_phone_from_sub(claims.get("sub"))
            if not phone:
                return _resp(403, {"error": "patient not provisioned"})
        else:                            # API-key path (POST / one-shot)
            if API_KEY:
                headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
                if headers.get("x-api-key") != API_KEY:
                    return _resp(401, {"error": "unauthorized"})
            phone = body.get("phone", "+254712345678")

        message = body.get("message")
        image_key = body.get("image_key")
        audio_key = body.get("audio_key")

        if path.endswith("/upload-url"):
            kind = body.get("type", "audio")
            ext = (body.get("ext") or ("webm" if kind == "audio" else "jpg")).lstrip(".")
            prefix = "chat-audio" if kind == "audio" else "images-in"
            key = f"{prefix}/{uuid.uuid4()}.{ext}"
            url = s3.generate_presigned_url("put_object",
                    Params={"Bucket": MEDIA_BUCKET, "Key": key}, ExpiresIn=900)
            return _resp(200, {"upload_url": url, "key": key})

        if path.endswith("/chat"):
            if not message and not image_key and not audio_key:
                return _resp(400, {"error": "message, image_key, or audio_key required"})
            return _resp(200, chat_turn(phone, message or "", session_id=body.get("session_id"),
                                        image_key=image_key, audio_key=audio_key,
                                        bucket=MEDIA_BUCKET, speak=body.get("speak"),
                                        lat=body.get("lat"), lng=body.get("lng")))

        if not message:
            return _resp(400, {"error": "message is required"})
        return _resp(200, run_triage(message, phone, emergency=bool(body.get("emergency", False))))
    except ValueError as e:
        return _resp(404, {"error": str(e)})
    except Exception as e:
        print(f"[error] {e}")
        return _resp(500, {"error": "internal error"})


def s3_handler(event, context):
    rec = event["Records"][0]
    bucket = rec["s3"]["bucket"]["name"]
    key = urllib.parse.unquote_plus(rec["s3"]["object"]["key"])
    if key.startswith("transcripts/") or key.startswith("audio-out/"):
        return {"skipped": key}
    head = s3.head_object(Bucket=bucket, Key=key)
    phone = head.get("Metadata", {}).get("phone", "+254712345678")
    print(f"[voice] transcribing s3://{bucket}/{key} for {phone}")
    text, lang = transcribe_s3(bucket, key)
    print(f"[voice] transcript [{lang}]: {text}")
    result = run_triage(text, phone, input_type="voice",
                        audio_s3_uri=f"s3://{bucket}/{key}")
    print(f"[voice] done. session {result['session_id']} ({result['session_type']})")
    return {"session_id": result["session_id"]}
