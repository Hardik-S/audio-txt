from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from .config import AudioTxtConfig
from .file_utils import atomic_write_text
from .transcribers.base import TranscriptionResult


def write_outputs(
    result: TranscriptionResult,
    *,
    source_path: Path,
    config: AudioTxtConfig,
    audio_hash: str,
) -> list[Path]:
    output_config = config.data["outputs"]
    transcripts_dir = config.path("transcripts_dir")
    base_stem = _choose_output_stem(
        transcripts_dir,
        source_path.stem,
        audio_hash,
        output_config,
    )

    written: list[Path] = []
    if output_config.get("txt", True):
        txt_path = transcripts_dir / f"{base_stem}.txt"
        atomic_write_text(txt_path, result.text.strip() + "\n")
        written.append(txt_path)

    if output_config.get("cleaned_txt", False):
        cleaned_path = transcripts_dir / f"{base_stem}.cleaned.txt"
        atomic_write_text(cleaned_path, clean_transcript(result.text, config).strip() + "\n")
        written.append(cleaned_path)

    if output_config.get("json", True):
        json_path = transcripts_dir / f"{base_stem}.json"
        payload = {
            "text": result.text,
            "segments": [asdict(segment) for segment in result.segments],
            "language": result.language,
            "language_probability": result.language_probability,
            "duration_seconds": result.duration_seconds,
            "engine": result.engine,
            "model": result.model,
            "created_at": result.created_at,
            "quality_flags": result.quality_flags,
            "source_file": str(source_path),
            "sha256": audio_hash,
        }
        atomic_write_text(json_path, json.dumps(payload, ensure_ascii=True, indent=2) + "\n")
        written.append(json_path)

    if output_config.get("srt", True):
        srt_path = transcripts_dir / f"{base_stem}.srt"
        atomic_write_text(srt_path, format_srt(result))
        written.append(srt_path)

    return written


def _choose_output_stem(
    transcripts_dir: Path,
    source_stem: str,
    audio_hash: str,
    output_config: dict[str, object],
) -> str:
    suffixes = []
    if output_config.get("txt", True):
        suffixes.append(".txt")
    if output_config.get("json", True):
        suffixes.append(".json")
    if output_config.get("srt", True):
        suffixes.append(".srt")
    if output_config.get("cleaned_txt", False):
        suffixes.append(".cleaned.txt")

    if not any((transcripts_dir / f"{source_stem}{suffix}").exists() for suffix in suffixes):
        return source_stem
    return f"{source_stem}.{audio_hash[:8]}"


def clean_transcript(text: str, config: AudioTxtConfig) -> str:
    cleaning = config.data["cleaning"]
    if not cleaning.get("remove_filler_words", False):
        return text
    cleaned = text
    for filler in cleaning.get("filler_words", []):
        cleaned = re.sub(rf"\b{re.escape(str(filler))}\b", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()


def format_srt(result: TranscriptionResult) -> str:
    lines: list[str] = []
    for index, segment in enumerate(result.segments, start=1):
        lines.append(str(index))
        lines.append(f"{format_srt_timestamp(segment.start)} --> {format_srt_timestamp(segment.end)}")
        lines.append(segment.text.strip())
        lines.append("")
    return "\n".join(lines)


def format_srt_timestamp(seconds: float) -> str:
    milliseconds_total = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds_total, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"
