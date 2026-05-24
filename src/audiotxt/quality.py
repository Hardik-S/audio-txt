from __future__ import annotations

from .config import AudioTxtConfig
from .transcribers.base import TranscriptionResult


def assess_quality(result: TranscriptionResult, config: AudioTxtConfig) -> list[str]:
    quality_config = config.data["quality"]
    if not quality_config.get("enabled", True):
        return []

    flags: list[str] = []
    if not result.text.strip():
        flags.append("empty_transcript")

    for segment in result.segments:
        if segment.end < segment.start:
            flags.append("segment_timing_invalid")
            break

    language_probability = result.language_probability
    if (
        language_probability is not None
        and language_probability < quality_config["low_language_probability_threshold"]
    ):
        flags.append("low_language_probability")

    if result.segments:
        max_no_speech = max(
            (segment.no_speech_prob for segment in result.segments if segment.no_speech_prob is not None),
            default=None,
        )
        if (
            max_no_speech is not None
            and max_no_speech > quality_config["high_no_speech_probability_threshold"]
        ):
            flags.append("high_no_speech_probability")

    if result.duration_seconds and result.duration_seconds > 0:
        chars_per_minute = len(result.text.strip()) / (result.duration_seconds / 60)
        if chars_per_minute < quality_config["min_text_chars_per_minute"]:
            flags.append("too_little_text")

    return flags
