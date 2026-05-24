from __future__ import annotations

import json

from audiotxt.config import load_config
from audiotxt.outputs import format_srt_timestamp, write_outputs
from audiotxt.transcribers.base import Segment, TranscriptionResult


def _result() -> TranscriptionResult:
    return TranscriptionResult(
        text="Hello world.",
        segments=[Segment(id=0, start=0.0, end=1.25, text="Hello world.")],
        language="en",
        language_probability=0.95,
        duration_seconds=1.25,
        engine="fake",
        model="fake-model",
        created_at="2026-05-24T00:00:00+00:00",
        quality_flags=[],
    )


def test_writes_txt_json_and_srt(tmp_path):
    config = load_config(base_dir=tmp_path)
    config.path("transcripts_dir").mkdir()

    written = write_outputs(
        _result(),
        source_path=tmp_path / "hello.wav",
        config=config,
        audio_hash="abcdef123456",
    )

    assert tmp_path / "transcripts" / "hello.txt" in written
    assert (tmp_path / "transcripts" / "hello.txt").read_text(encoding="utf-8") == "Hello world.\n"
    payload = json.loads((tmp_path / "transcripts" / "hello.json").read_text(encoding="utf-8"))
    assert payload["segments"][0]["text"] == "Hello world."
    assert "00:00:00,000 --> 00:00:01,250" in (
        tmp_path / "transcripts" / "hello.srt"
    ).read_text(encoding="utf-8")


def test_output_collision_appends_short_hash(tmp_path):
    config = load_config(base_dir=tmp_path)
    transcripts = config.path("transcripts_dir")
    transcripts.mkdir()
    (transcripts / "hello.txt").write_text("existing", encoding="utf-8")

    write_outputs(
        _result(),
        source_path=tmp_path / "hello.wav",
        config=config,
        audio_hash="abcdef123456",
    )

    assert (transcripts / "hello.abcdef12.txt").exists()


def test_srt_timestamp_formatting():
    assert format_srt_timestamp(3661.234) == "01:01:01,234"
