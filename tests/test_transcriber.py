from __future__ import annotations

import sys
import types

from audiotxt.config import load_config
from audiotxt.transcribers.faster_whisper_transcriber import FasterWhisperTranscriber
from audiotxt.transcribers.gemini_transcriber import GeminiTranscriber


def test_faster_whisper_forces_segment_iteration(monkeypatch, tmp_path):
    consumed = {"value": False}

    class RawSegment:
        id = 0
        start = 0.0
        end = 1.0
        text = " Hello "
        avg_logprob = None
        no_speech_prob = None
        compression_ratio = None

    class Info:
        language = "en"
        language_probability = 0.9
        duration = 1.0

    def segment_generator():
        consumed["value"] = True
        yield RawSegment()

    class WhisperModel:
        instances = 0

        def __init__(self, *args, **kwargs):
            WhisperModel.instances += 1

        def transcribe(self, *args, **kwargs):
            return segment_generator(), Info()

    module = types.SimpleNamespace(WhisperModel=WhisperModel)
    monkeypatch.setitem(sys.modules, "faster_whisper", module)

    config = load_config(base_dir=tmp_path)
    transcriber = FasterWhisperTranscriber(config)
    result = transcriber.transcribe(tmp_path / "clip.wav")
    second = transcriber.transcribe(tmp_path / "clip2.wav")

    assert consumed["value"]
    assert result.text == "Hello"
    assert second.model == "small.en"
    assert WhisperModel.instances == 1


def test_gemini_disabled_errors_without_google_import(tmp_path):
    config = load_config(base_dir=tmp_path)

    try:
        GeminiTranscriber(config).transcribe(tmp_path / "clip.wav")
    except RuntimeError as exc:
        assert "disabled" in str(exc)
    else:
        raise AssertionError("GeminiTranscriber should fail when disabled")
