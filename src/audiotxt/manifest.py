from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Manifest:
    def __init__(self, path: Path):
        self.path = path

    def success_hashes(self) -> set[str]:
        hashes: set[str] = set()
        for entry in self.iter_entries():
            if entry.get("status") == "success" and entry.get("sha256"):
                hashes.add(str(entry["sha256"]))
        return hashes

    def has_success(self, audio_hash: str) -> bool:
        return audio_hash in self.success_hashes()

    def iter_entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                entries.append(parsed)
        return entries

    def append(self, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {"timestamp": utc_now(), **entry}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")

    def record_success(
        self,
        *,
        source_path: Path,
        processed_path: Path,
        transcript_paths: list[Path],
        audio_hash: str,
        engine: str,
        model: str,
    ) -> None:
        self.append(
            {
                "status": "success",
                "source_path": str(source_path),
                "processed_path": str(processed_path),
                "transcript_paths": [str(path) for path in transcript_paths],
                "sha256": audio_hash,
                "engine": engine,
                "model": model,
            }
        )

    def record_failure(
        self,
        *,
        source_path: Path,
        failed_path: Path | None,
        error_path: Path,
        audio_hash: str | None,
        engine: str,
        model: str,
        exception_type: str,
        exception_message: str,
    ) -> None:
        self.append(
            {
                "status": "failure",
                "source_path": str(source_path),
                "failed_path": str(failed_path) if failed_path else None,
                "error_path": str(error_path),
                "sha256": audio_hash,
                "engine": engine,
                "model": model,
                "exception_type": exception_type,
                "exception_message": exception_message,
            }
        )

    def record_duplicate(self, *, source_path: Path, duplicate_path: Path, audio_hash: str) -> None:
        self.append(
            {
                "status": "duplicate",
                "source_path": str(source_path),
                "duplicate_path": str(duplicate_path),
                "sha256": audio_hash,
            }
        )
