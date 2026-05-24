from __future__ import annotations

from audiotxt.config import load_config
from audiotxt.pipeline import AudioTxtPipeline
from audiotxt.transcribers.base import Segment, TranscriptionResult


class FakeTranscriber:
    def __init__(self):
        self.calls = 0

    def transcribe(self, audio_path):
        self.calls += 1
        return TranscriptionResult(
            text="Fake transcript.",
            segments=[Segment(id=0, start=0, end=1, text="Fake transcript.")],
            language="en",
            language_probability=0.99,
            duration_seconds=1,
            engine="fake",
            model="fake-model",
            created_at="2026-05-24T00:00:00+00:00",
            quality_flags=[],
        )


def _config(tmp_path):
    config = load_config(base_dir=tmp_path)
    config.data["audio"]["file_settle_seconds"] = 0
    return config


def test_pipeline_processes_successful_file(tmp_path):
    fake = FakeTranscriber()
    config = _config(tmp_path)
    pipeline = AudioTxtPipeline(config, transcriber_factory=lambda _config: fake)
    pipeline.initialize_folders()
    (config.path("input_dir") / "clip.wav").write_bytes(b"audio")

    stats = pipeline.run_once()

    assert stats["processed"] == 1
    assert (config.path("processed_dir") / "clip.wav").exists()
    assert (config.path("transcripts_dir") / "clip.txt").exists()
    assert fake.calls == 1


def test_pipeline_file_argument_only_processes_requested_file(tmp_path):
    fake = FakeTranscriber()
    config = _config(tmp_path)
    pipeline = AudioTxtPipeline(config, transcriber_factory=lambda _config: fake)
    pipeline.initialize_folders()
    queued = config.path("input_dir") / "queued.wav"
    queued.write_bytes(b"queued")
    external = tmp_path / "external.wav"
    external.write_bytes(b"external")

    stats = pipeline.run_once(file_path=external)

    assert stats["processed"] == 1
    assert queued.exists()
    assert (config.path("processed_dir") / "external.wav").exists()
    assert fake.calls == 1


def test_pipeline_dry_run_file_argument_does_not_ingest_external_file(tmp_path):
    fake = FakeTranscriber()
    config = _config(tmp_path)
    pipeline = AudioTxtPipeline(config, transcriber_factory=lambda _config: fake)
    pipeline.initialize_folders()
    external = tmp_path / "external.wav"
    external.write_bytes(b"external")

    stats = pipeline.run_once(file_path=external, dry_run=True)

    assert stats == {"processed": 0, "failed": 0, "duplicates": 0, "candidates": 1}
    assert not (config.path("input_dir") / "external.wav").exists()
    assert external.exists()
    assert fake.calls == 0


def test_pipeline_skips_duplicate_to_duplicates_folder(tmp_path):
    fake = FakeTranscriber()
    config = _config(tmp_path)
    pipeline = AudioTxtPipeline(config, transcriber_factory=lambda _config: fake)
    pipeline.initialize_folders()
    first = config.path("input_dir") / "clip.wav"
    first.write_bytes(b"same")
    pipeline.run_once()

    second = config.path("input_dir") / "again.wav"
    second.write_bytes(b"same")
    stats = pipeline.run_once()

    assert stats["duplicates"] == 1
    assert (config.path("processed_dir") / "duplicates" / "again.wav").exists()
    assert fake.calls == 1


def test_pipeline_moves_failures_and_writes_error(tmp_path):
    class BrokenTranscriber:
        def transcribe(self, audio_path):
            raise RuntimeError("boom")

    config = _config(tmp_path)
    pipeline = AudioTxtPipeline(config, transcriber_factory=lambda _config: BrokenTranscriber())
    pipeline.initialize_folders()
    (config.path("input_dir") / "bad.wav").write_bytes(b"audio")

    stats = pipeline.run_once()

    assert stats["failed"] == 1
    assert (config.path("failed_dir") / "bad.wav").exists()
    assert (config.path("failed_dir") / "bad.error.txt").exists()


def test_pipeline_recovers_stranded_processing_file(tmp_path):
    config = _config(tmp_path)
    pipeline = AudioTxtPipeline(config, transcriber_factory=lambda _config: FakeTranscriber())
    pipeline.initialize_folders()
    (config.path("processing_dir") / "stranded.wav").write_bytes(b"audio")

    recovered = pipeline.recover_processing()

    assert recovered == [config.path("input_dir") / "stranded.wav"]
    assert recovered[0].exists()
