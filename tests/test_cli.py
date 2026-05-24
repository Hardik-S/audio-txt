from __future__ import annotations

from pathlib import Path

from audiotxt import cli
from audiotxt.cli import build_parser


def test_config_option_works_after_watch_subcommand():
    args = build_parser().parse_args(["watch", "--config", "custom.yaml"])

    assert args.command == "watch"
    assert args.config == "custom.yaml"


def test_config_option_works_after_transcribe_subcommand():
    args = build_parser().parse_args(["transcribe", "--config", "custom.yaml", "--dry-run"])

    assert args.command == "transcribe"
    assert args.config == "custom.yaml"
    assert args.dry_run is True


def test_top_level_config_option_still_works():
    args = build_parser().parse_args(["--config", "custom.yaml", "transcribe"])

    assert args.command == "transcribe"
    assert args.config == "custom.yaml"


def test_gui_command_parses_config_after_subcommand():
    args = build_parser().parse_args(["gui", "--config", "custom.yaml"])

    assert args.command == "gui"
    assert args.config == "custom.yaml"


def test_gui_command_creates_default_config_before_launch(monkeypatch, tmp_path):
    launched: list[Path] = []

    def fake_launch(config_path: Path) -> int:
        launched.append(config_path)
        return 0

    monkeypatch.setattr("audiotxt.gui.launch_gui", fake_launch)

    exit_code = cli.main(["gui", "--config", str(tmp_path / "config.yaml")])

    assert exit_code == 0
    assert launched == [tmp_path / "config.yaml"]
    assert (tmp_path / "config.yaml").exists()
