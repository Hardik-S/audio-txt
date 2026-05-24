from __future__ import annotations

import hashlib
import os
import shutil
import time
from pathlib import Path

TEMP_SUFFIXES = (".tmp", ".part", ".partial", ".crdownload", ".download")


def is_ignored_file(path: Path) -> bool:
    name = path.name
    return (
        name.startswith(".")
        or name.startswith("~$")
        or name.endswith(TEMP_SUFFIXES)
        or not path.is_file()
    )


def is_supported_audio(path: Path, supported_extensions: set[str]) -> bool:
    return path.suffix.lower() in supported_extensions and not is_ignored_file(path)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_snapshot(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def is_locked(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        with path.open("rb"):
            return False
    except OSError:
        return True


def wait_for_stability(
    path: Path,
    settle_seconds: float,
    *,
    poll_seconds: float = 0.5,
    max_wait_seconds: float | None = None,
) -> bool:
    if settle_seconds <= 0:
        return path.exists() and path.is_file() and not is_locked(path)

    deadline = time.monotonic() + (
        max_wait_seconds if max_wait_seconds is not None else max(10.0, settle_seconds * 3)
    )
    last_snapshot: tuple[int, int] | None = None
    stable_since: float | None = None

    while time.monotonic() <= deadline:
        if not path.exists() or not path.is_file() or is_locked(path):
            last_snapshot = None
            stable_since = None
            time.sleep(poll_seconds)
            continue

        current = file_snapshot(path)
        now = time.monotonic()
        if current == last_snapshot:
            if stable_since is not None and now - stable_since >= settle_seconds:
                return True
        else:
            stable_since = now
            last_snapshot = current
        time.sleep(poll_seconds)

    return False


def ensure_unique_path(path: Path, *, suffix: str | None = None) -> Path:
    if not path.exists():
        return path
    suffix_text = suffix or str(int(time.time()))
    candidate = path.with_name(f"{path.stem}.{suffix_text}{path.suffix}")
    index = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}.{suffix_text}.{index}{path.suffix}")
        index += 1
    return candidate


def atomic_move(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    final_destination = ensure_unique_path(destination)
    return Path(shutil.move(str(source), str(final_destination)))


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    os.replace(temp_path, path)
