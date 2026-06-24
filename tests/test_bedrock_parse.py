"""Tests for the defensive JSON parsing in shared.bedrock."""
import pytest

from shared.bedrock import _parse_json


def test_parses_plain_json():
    assert _parse_json('{"a": 1}') == {"a": 1}


def test_strips_markdown_fences():
    raw = '```json\n{"severity": "high"}\n```'
    assert _parse_json(raw) == {"severity": "high"}


def test_slices_object_out_of_surrounding_prose():
    raw = 'Here is the briefing:\n{"chief_complaint": "burn"}\nThanks!'
    assert _parse_json(raw) == {"chief_complaint": "burn"}


def test_raises_on_garbage():
    with pytest.raises(ValueError):
        _parse_json("not json at all")
