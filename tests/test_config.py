from __future__ import annotations

import pytest

from audiotxt.config import load_config


def test_loads_default_config(tmp_path):
    config = load_config(base_dir=tmp_path)

    assert config.data["local"]["model_size"] == "small.en"
    assert config.path("input_dir") == tmp_path / "input_audio"
    assert ".wav" in config.supported_extensions


def test_rejects_missing_required_paths(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
paths:
  input_dir: input_audio
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing required path keys"):
        load_config(config_path)


def test_normalizes_extensions_to_lowercase_with_dot(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
audio:
  supported_extensions:
    - WAV
    - .Mp3
    - ""
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.data["audio"]["supported_extensions"] == [".wav", ".mp3"]


def test_language_auto_detection_switches_english_only_model(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
local:
  model_size: medium.en
  language: null
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.data["local"]["model_size"] == "medium"
    assert config.warnings == [
        "language is null, so English-only model medium.en was changed to medium"
    ]
