"""Canonical database enum values and normalisers.

These mirror the CHECK constraints on the live Aurora schema. Centralising them
here means the Lambdas never write a value the database will reject. If a
constraint changes, update it in this one place.
"""
from __future__ import annotations

from shared.logging_utils import get_logger

logger = get_logger(__name__)

# clinical_briefings.severity CHECK: mild | moderate | severe | critical
ALLOWED_SEVERITY = ("mild", "moderate", "severe", "critical")

# clinical_briefings.processing_status CHECK: raw | partial | complete
PROCESSING_STATUS_COMPLETE = "complete"

# patients.literacy_level CHECK: standard | low_literacy
# sessions.status CHECK: active | completed | escalated
# clinical_briefings.clinician_decision CHECK: accepted | modified | rejected

# Map the vocabulary a model is likely to emit onto the allowed severities.
_SEVERITY_MAP = {
    "low": "mild",
    "minimal": "mild",
    "mild": "mild",
    "moderate": "moderate",
    "medium": "moderate",
    "high": "severe",
    "severe": "severe",
    "serious": "severe",
    "critical": "critical",
    "emergency": "critical",
    "life-threatening": "critical",
}


def normalize_severity(value: str | None, default: str = "moderate") -> str:
    """Coerce a model-produced severity into an allowed DB value.

    Defaults to 'moderate' (a safe middle ground) and logs when it has to,
    so we never fail a clinical write on a vocabulary mismatch.
    """
    if value:
        mapped = _SEVERITY_MAP.get(str(value).strip().lower())
        if mapped:
            return mapped
    logger.warning(
        "severity_normalised_to_default",
        extra={"extra": {"received": value, "default": default}},
    )
    return default
