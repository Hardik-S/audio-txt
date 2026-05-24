from __future__ import annotations

from audiotxt.manifest import Manifest


def test_records_success_and_detects_duplicate_hash(tmp_path):
    manifest = Manifest(tmp_path / "manifest.jsonl")

    manifest.record_success(
        source_path=tmp_path / "input.wav",
        processed_path=tmp_path / "processed.wav",
        transcript_paths=[tmp_path / "input.txt"],
        audio_hash="abc123",
        engine="fake",
        model="fake-model",
    )

    assert manifest.has_success("abc123")
    assert not manifest.has_success("missing")


def test_handles_missing_manifest(tmp_path):
    manifest = Manifest(tmp_path / "missing.jsonl")

    assert manifest.iter_entries() == []
    assert not manifest.has_success("abc")


def test_handles_malformed_manifest_lines(tmp_path):
    path = tmp_path / "manifest.jsonl"
    path.write_text('{"status":"success","sha256":"ok"}\nnot-json\n', encoding="utf-8")
    manifest = Manifest(path)

    assert manifest.has_success("ok")
