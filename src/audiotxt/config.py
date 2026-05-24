from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "paths": {
        "input_dir": "input_audio",
        "processing_dir": "processing",
        "transcripts_dir": "transcripts",
        "processed_dir": "processed_audio",
        "failed_dir": "failed_audio",
        "logs_dir": "logs",
    },
    "audio": {
        "supported_extensions": [".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"],
        "file_settle_seconds": 8,
        "max_retries": 1,
    },
    "engine": {"mode": "local"},
    "local": {
        "provider": "faster-whisper",
        "model_size": "small.en",
        "device": "cpu",
        "compute_type": "int8",
        "language": "en",
        "task": "transcribe",
        "beam_size": 5,
        "vad_filter": True,
        "condition_on_previous_text": False,
    },
    "quality": {
        "enabled": True,
        "low_language_probability_threshold": 0.60,
        "high_no_speech_probability_threshold": 0.65,
        "min_text_chars_per_minute": 20,
    },
    "outputs": {
        "txt": True,
        "json": True,
        "srt": True,
        "cleaned_txt": False,
        "preserve_original_text": True,
    },
    "cleaning": {
        "remove_filler_words": False,
        "filler_words": ["um", "uh", "like", "you know"],
    },
    "watch": {"poll_seconds": 5, "stop_after_empty_cycles": None},
    "duplicates": {
        "enabled": True,
        "hash_algorithm": "sha256",
        "manifest_file": "logs/manifest.jsonl",
    },
    "gemini": {
        "enabled": False,
        "model": "gemini-3.5-flash",
        "api_key_env": "GEMINI_API_KEY",
        "use_files_api_over_mb": 18,
        "prompt": (
            "Generate a verbatim transcript of the speech in this audio file.\n"
            "Preserve wording. Do not summarize. Do not add commentary.\n"
            "If possible, include timestamps. Return plain transcript text.\n"
        ),
    },
    "presets": {
        "fast": {"model_size": "base.en", "compute_type": "int8", "language": "en"},
        "balanced": {"model_size": "small.en", "compute_type": "int8", "language": "en"},
        "accurate": {"model_size": "medium.en", "compute_type": "int8", "language": "en"},
        "multilingual": {"model_size": "small", "compute_type": "int8", "language": None},
    },
}

REQUIRED_PATH_KEYS = {
    "input_dir",
    "processing_dir",
    "transcripts_dir",
    "processed_dir",
    "failed_dir",
    "logs_dir",
}


@dataclass
class AudioTxtConfig:
    data: dict[str, Any]
    root_dir: Path
    config_path: Path | None = None
    warnings: list[str] = field(default_factory=list)

    def path(self, key: str) -> Path:
        value = self.data["paths"][key]
        return self.resolve_path(value)

    def resolve_path(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return self.root_dir / path

    @property
    def manifest_path(self) -> Path:
        return self.resolve_path(self.data["duplicates"]["manifest_file"])

    @property
    def supported_extensions(self) -> set[str]:
        return set(self.data["audio"]["supported_extensions"])


def default_config_yaml() -> str:
    return yaml.safe_dump(DEFAULT_CONFIG, sort_keys=False, allow_unicode=False)


def write_default_config(config_path: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        config_path.write_text(default_config_yaml(), encoding="utf-8")


def load_config(
    config_path: str | Path | None = None,
    *,
    model_override: str | None = None,
    base_dir: str | Path | None = None,
) -> AudioTxtConfig:
    path = Path(config_path) if config_path else None
    root_dir = Path(base_dir) if base_dir else Path.cwd()
    if path is not None:
        if not path.is_absolute():
            path = root_dir / path
        root_dir = path.parent

    data = deepcopy(DEFAULT_CONFIG)
    if path is not None and path.exists():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"Config file must contain a mapping: {path}")
        if "paths" in loaded:
            _validate_paths(loaded)
        data = _deep_merge(data, loaded)

    if model_override:
        data["local"]["model_size"] = model_override

    warnings: list[str] = []
    _validate_paths(data)
    _normalize_extensions(data)
    _normalize_model_language(data, warnings)

    return AudioTxtConfig(data=data, root_dir=root_dir, config_path=path, warnings=warnings)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _validate_paths(data: dict[str, Any]) -> None:
    paths = data.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("Config must include a paths mapping.")
    missing = sorted(REQUIRED_PATH_KEYS - set(paths))
    if missing:
        raise ValueError(f"Config is missing required path keys: {', '.join(missing)}")


def _normalize_extensions(data: dict[str, Any]) -> None:
    raw_extensions = data["audio"].get("supported_extensions", [])
    normalized: list[str] = []
    for ext in raw_extensions:
        ext_text = str(ext).strip().lower()
        if not ext_text:
            continue
        if not ext_text.startswith("."):
            ext_text = f".{ext_text}"
        if ext_text not in normalized:
            normalized.append(ext_text)
    data["audio"]["supported_extensions"] = normalized


def _normalize_model_language(data: dict[str, Any], warnings: list[str]) -> None:
    local = data["local"]
    model_size = str(local.get("model_size", "small.en"))
    if local.get("language") is None and model_size.endswith(".en"):
        multilingual = model_size.removesuffix(".en")
        local["model_size"] = multilingual
        warnings.append(
            f"language is null, so English-only model {model_size} was changed to {multilingual}"
        )
