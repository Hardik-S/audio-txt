from __future__ import annotations

import shutil
import struct
import tempfile
import wave
from pathlib import Path

from audiotxt.config import load_config
from audiotxt.pipeline import AudioTxtPipeline
from audiotxt.transcribers.base import Segment, TranscriptionResult


class SmokeTranscriber:
    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        return TranscriptionResult(
            text="",
            segments=[Segment(id=0, start=0.0, end=1.0, text="")],
            language="en",
            language_probability=1.0,
            duration_seconds=1.0,
            engine="smoke-fake",
            model="smoke-fake",
            created_at="2026-05-24T00:00:00+00:00",
            quality_flags=[],
        )


def generate_silent_wav(path: Path) -> None:
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        for _ in range(16000):
            handle.writeframes(struct.pack("<h", 0))


def main() -> int:
    workspace = Path(tempfile.mkdtemp(prefix="audiotxt-smoke-"))
    try:
        config = load_config(base_dir=workspace)
        config.data["audio"]["file_settle_seconds"] = 0
        pipeline = AudioTxtPipeline(config, transcriber_factory=lambda _config: SmokeTranscriber())
        pipeline.initialize_folders()
        generate_silent_wav(config.path("input_dir") / "silence.wav")

        stats = pipeline.run_once()
        assert stats["processed"] == 1, stats
        assert (config.path("processed_dir") / "silence.wav").exists()
        assert (config.path("transcripts_dir") / "silence.txt").exists()
        assert config.manifest_path.exists()
        print(f"Smoke test passed in {workspace}")
        return 0
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
