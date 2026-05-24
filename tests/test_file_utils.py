from __future__ import annotations

from audiotxt.file_utils import (
    atomic_move,
    atomic_write_text,
    is_supported_audio,
    sha256_file,
    wait_for_stability,
)


def test_detects_supported_files(tmp_path):
    audio = tmp_path / "clip.WAV"
    audio.write_bytes(b"audio")
    text = tmp_path / "clip.txt"
    text.write_text("no", encoding="utf-8")

    assert is_supported_audio(audio, {".wav"})
    assert not is_supported_audio(text, {".wav"})


def test_ignores_temp_files(tmp_path):
    partial = tmp_path / "clip.wav.tmp"
    partial.write_bytes(b"partial")

    assert not is_supported_audio(partial, {".tmp"})


def test_wait_for_stability_detects_existing_file(tmp_path):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"audio")

    assert wait_for_stability(audio, 0)


def test_sha256_file(tmp_path):
    path = tmp_path / "data.bin"
    path.write_bytes(b"abc")

    assert sha256_file(path) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_atomic_move_avoids_overwrite(tmp_path):
    source = tmp_path / "source.wav"
    source.write_bytes(b"new")
    destination = tmp_path / "done.wav"
    destination.write_bytes(b"old")

    moved = atomic_move(source, destination)

    assert moved.name != "done.wav"
    assert moved.read_bytes() == b"new"
    assert destination.read_bytes() == b"old"


def test_atomic_write_text(tmp_path):
    path = tmp_path / "out.txt"

    atomic_write_text(path, "hello")

    assert path.read_text(encoding="utf-8") == "hello"
    assert not (tmp_path / "out.txt.tmp").exists()
