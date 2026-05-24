from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config, write_default_config
from .pipeline import AudioTxtPipeline
from .watcher import watch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="audiotxt", description="Folder-drop audio transcription.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create missing folders and default config.")
    init_parser.add_argument("--config", default=argparse.SUPPRESS, help="Path to config.yaml.")

    transcribe_parser = subparsers.add_parser("transcribe", help="Process waiting files once.")
    transcribe_parser.add_argument("--config", default=argparse.SUPPRESS, help="Path to config.yaml.")
    transcribe_parser.add_argument("--file", dest="file_path", help="Specific audio file to ingest.")
    transcribe_parser.add_argument("--model", help="Override local faster-whisper model size.")
    transcribe_parser.add_argument("--dry-run", action="store_true", help="Print files without moving them.")

    watch_parser = subparsers.add_parser("watch", help="Poll input_audio and process new files.")
    watch_parser.add_argument("--config", default=argparse.SUPPRESS, help="Path to config.yaml.")
    watch_parser.add_argument("--model", help="Override local faster-whisper model size.")

    gui_parser = subparsers.add_parser("gui", help="Open the AudioTxt desktop interface.")
    gui_parser.add_argument("--config", default=argparse.SUPPRESS, help="Path to config.yaml.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config_path = Path(args.config)

    if args.command == "init":
        write_default_config(config_path)
        config = load_config(config_path)
        pipeline = AudioTxtPipeline(config)
        pipeline.initialize_folders()
        for warning in config.warnings:
            pipeline.logger.warning(warning)
        print(f"Initialized AudioTxt folders using {config_path}")
        return 0

    model_override = getattr(args, "model", None)
    config = load_config(config_path, model_override=model_override)
    pipeline = AudioTxtPipeline(config)
    for warning in config.warnings:
        pipeline.logger.warning(warning)

    if args.command == "transcribe":
        stats = pipeline.run_once(
            file_path=Path(args.file_path) if args.file_path else None,
            dry_run=bool(args.dry_run),
        )
        print(
            "processed={processed} failed={failed} duplicates={duplicates} candidates={candidates}".format(
                **stats
            )
        )
        return 0

    if args.command == "watch":
        watch(pipeline)
        return 0

    if args.command == "gui":
        write_default_config(config_path)
        try:
            from .gui import launch_gui
        except ImportError as exc:
            parser.exit(1, f"AudioTxt GUI requires tkinter, but it is unavailable: {exc}\n")
        return launch_gui(config_path)

    parser.error(f"Unknown command: {args.command}")
    return 2
