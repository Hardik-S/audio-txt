from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import AudioTxtConfig
from ..quality import assess_quality
from .base import Segment, TranscriptionResult


class FasterWhisperTranscriber:
    def __init__(self, config: AudioTxtConfig):
        self.config = config
        self._model: Any | None = None

    @property
    def model_size(self) -> str:
        return str(self.config.data["local"]["model_size"])

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        local_config = self.config.data["local"]
        model = self._get_model()
        raw_segments, info = model.transcribe(
            str(audio_path),
            beam_size=int(local_config["beam_size"]),
            language=local_config.get("language"),
            task=str(local_config.get("task", "transcribe")),
            vad_filter=bool(local_config.get("vad_filter", True)),
            condition_on_previous_text=bool(
                local_config.get("condition_on_previous_text", False)
            ),
        )
        segment_list = list(raw_segments)
        segments = [
            Segment(
                id=int(getattr(segment, "id", index)),
                start=float(getattr(segment, "start", 0.0)),
                end=float(getattr(segment, "end", 0.0)),
                text=str(getattr(segment, "text", "")).strip(),
                avg_logprob=getattr(segment, "avg_logprob", None),
                no_speech_prob=getattr(segment, "no_speech_prob", None),
                compression_ratio=getattr(segment, "compression_ratio", None),
            )
            for index, segment in enumerate(segment_list)
        ]
        text = " ".join(segment.text for segment in segments).strip()
        result = TranscriptionResult(
            text=text,
            segments=segments,
            language=getattr(info, "language", None),
            language_probability=getattr(info, "language_probability", None),
            duration_seconds=getattr(info, "duration", None),
            engine="faster-whisper",
            model=self.model_size,
            created_at=datetime.now(timezone.utc).isoformat(),
            quality_flags=[],
        )
        result.quality_flags = assess_quality(result, self.config)
        return result

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError(
                    "faster-whisper is not installed. Run `python -m pip install -r requirements.txt`."
                ) from exc

            local_config = self.config.data["local"]
            self._model = WhisperModel(
                self.model_size,
                device=str(local_config["device"]),
                compute_type=str(local_config["compute_type"]),
            )
        return self._model
