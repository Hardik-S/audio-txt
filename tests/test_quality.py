from __future__ import annotations

from audiotxt.config import load_config
from audiotxt.quality import assess_quality
from audiotxt.transcribers.base import Segment, TranscriptionResult


def _result(**overrides):
    base = dict(
        text="Hello",
        segments=[Segment(id=0, start=0, end=1, text="Hello")],
        language="en",
        language_probability=0.99,
        duration_seconds=1,
        engine="fake",
        model="fake",
        created_at="2026-05-24T00:00:00+00:00",
        quality_flags=[],
    )
    base.update(overrides)
    return TranscriptionResult(**base)


def test_quality_empty_transcript(tmp_path):
    config = load_config(base_dir=tmp_path)

    flags = assess_quality(_result(text="   "), config)

    assert "empty_transcript" in flags


def test_quality_low_language_probability(tmp_path):
    config = load_config(base_dir=tmp_path)

    flags = assess_quality(_result(language_probability=0.2), config)

    assert "low_language_probability" in flags


def test_quality_too_little_text(tmp_path):
    config = load_config(base_dir=tmp_path)

    flags = assess_quality(_result(text="Hi", duration_seconds=120), config)

    assert "too_little_text" in flags


def test_quality_invalid_segment_timing(tmp_path):
    config = load_config(base_dir=tmp_path)

    flags = assess_quality(
        _result(segments=[Segment(id=0, start=2.0, end=1.0, text="bad")]),
        config,
    )

    assert "segment_timing_invalid" in flags
