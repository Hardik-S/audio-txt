from __future__ import annotations

import os
from pathlib import Path

from ..config import AudioTxtConfig
from .base import TranscriptionResult


class GeminiTranscriber:
    def __init__(self, config: AudioTxtConfig):
        self.config = config

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        gemini_config = self.config.data["gemini"]
        api_key_env = str(gemini_config.get("api_key_env", "GEMINI_API_KEY"))
        if not gemini_config.get("enabled", False):
            raise RuntimeError("Gemini mode is disabled in config.yaml.")
        if not os.getenv(api_key_env):
            raise RuntimeError(f"Gemini mode requires the {api_key_env} environment variable.")
        raise NotImplementedError(
            "Gemini transcription is scaffolded but not implemented in the MVP. "
            "Use engine.mode: local for offline transcription."
        )
