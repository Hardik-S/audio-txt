from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class Segment:
    id: int
    start: float
    end: float
    text: str
    avg_logprob: float | None = None
    no_speech_prob: float | None = None
    compression_ratio: float | None = None


@dataclass
class TranscriptionResult:
    text: str
    segments: list[Segment]
    language: str | None
    language_probability: float | None
    duration_seconds: float | None
    engine: str
    model: str
    created_at: str
    quality_flags: list[str] = field(default_factory=list)


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        ...
