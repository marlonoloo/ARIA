"""Tests for severity normalisation against the DB CHECK constraint."""
import pytest

from shared.enums import ALLOWED_SEVERITY, normalize_severity


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("high", "severe"),
        ("HIGH", "severe"),
        ("low", "mild"),
        ("moderate", "moderate"),
        ("critical", "critical"),
        ("emergency", "critical"),
        ("severe", "severe"),
    ],
)
def test_known_values_map_to_allowed(raw, expected):
    assert normalize_severity(raw) == expected


def test_unknown_falls_back_to_default():
    assert normalize_severity("banana") == "moderate"


def test_none_falls_back_to_default():
    assert normalize_severity(None) == "moderate"


def test_all_outputs_are_db_allowed():
    for raw in ["high", "low", "moderate", "critical", None, "weird"]:
        assert normalize_severity(raw) in ALLOWED_SEVERITY
