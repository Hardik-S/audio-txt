from __future__ import annotations

from pathlib import Path
import threading
import time

from audiotxt.gui import GuiController, format_stats
from audiotxt.transcribers.base import Segment, TranscriptionResult


class FakeTranscriber:
    def __init__(self):
        self.calls = 0

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        self.calls += 1
        return TranscriptionResult(
            text="GUI transcript.",
            segments=[Segment(id=0, start=0, end=1, text="GUI transcript.")],
            language="en",
            language_probability=0.99,
            duration_seconds=1,
            engine="fake",
            model="fake",
            created_at="2026-05-24T00:00:00+00:00",
            quality_flags=[],
        )


def test_format_stats():
    assert (
        format_stats("Done", {"processed": 1, "failed": 0, "duplicates": 2, "candidates": 3})
        == "Done: processed 1, failed 0, duplicates 2, candidates 3"
    )


def test_controller_applies_gui_settings(tmp_path):
    events: list[str] = []
    controller = GuiController(tmp_path / "config.yaml", event_sink=events.append)

    controller.apply_settings(
        model="medium.en",
        language_mode="Auto",
        txt=True,
        json_output=False,
        srt=False,
        cleaned_txt=True,
    )

    assert controller.config.data["local"]["model_size"] == "medium"
    assert controller.config.data["local"]["language"] is None
    assert controller.config.data["outputs"]["json"] is False
    assert controller.config.data["outputs"]["cleaned_txt"] is True
    assert events == ["Auto language uses multilingual model: medium.en -> medium"]


def test_controller_resets_cached_transcriber_when_model_changes(tmp_path):
    controller = GuiController(tmp_path / "config.yaml")
    marker = object()
    controller.pipeline._transcriber = marker

    controller.apply_settings(
        model="medium.en",
        language_mode="English",
        txt=True,
        json_output=True,
        srt=True,
        cleaned_txt=False,
    )

    assert controller.pipeline._transcriber is None


def test_controller_requires_at_least_one_output(tmp_path):
    controller = GuiController(tmp_path / "config.yaml")

    try:
        controller.apply_settings(
            model="small.en",
            language_mode="English",
            txt=False,
            json_output=False,
            srt=False,
            cleaned_txt=False,
        )
    except ValueError as exc:
        assert "output" in str(exc)
    else:
        raise AssertionError("apply_settings should reject no selected outputs")


def test_controller_processes_file_with_existing_pipeline_boundary(tmp_path):
    events: list[str] = []
    fake = FakeTranscriber()
    controller = GuiController(tmp_path / "config.yaml", event_sink=events.append)
    controller.config.data["audio"]["file_settle_seconds"] = 0
    controller.pipeline._transcriber_factory = lambda _config: fake
    controller.initialize()
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"audio")

    stats = controller.process_file(audio)

    assert stats["processed"] == 1
    assert fake.calls == 1
    assert (controller.config.path("processed_dir") / "sample.wav").exists()
    assert (controller.config.path("transcripts_dir") / "sample.txt").exists()
    assert any("sample.wav" in event for event in events)


def test_watch_loop_serializes_pipeline_and_stops(tmp_path):
    events: list[str] = []
    controller = GuiController(tmp_path / "config.yaml", event_sink=events.append)
    calls = {"count": 0}

    def slow_run_once():
        calls["count"] += 1
        time.sleep(0.05)
        return {"processed": 0, "failed": 0, "duplicates": 0, "candidates": 0}

    controller.pipeline.run_once = slow_run_once  # type: ignore[method-assign]
    thread = threading.Thread(target=lambda: controller.watch_loop(poll_seconds=0.01))
    thread.start()
    time.sleep(0.02)
    controller.stop_watch()
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert calls["count"] >= 1
    assert "Watch folder stopped." in events
    assert "__status__:Ready" in events


def test_watch_loop_reports_exceptions_and_resets_status(tmp_path):
    events: list[str] = []
    controller = GuiController(tmp_path / "config.yaml", event_sink=events.append)

    def broken_run_once():
        raise RuntimeError("boom")

    controller.pipeline.run_once = broken_run_once  # type: ignore[method-assign]

    controller.watch_loop(poll_seconds=0.01)

    assert "Watch error: boom" in events
    assert "Watch folder stopped." in events
    assert "__status__:Ready" in events
