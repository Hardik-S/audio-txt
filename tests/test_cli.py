from __future__ import annotations

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
