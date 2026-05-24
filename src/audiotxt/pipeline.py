from __future__ import annotations

import logging
import shutil
import traceback
from pathlib import Path
from typing import Callable

from .config import AudioTxtConfig
from .file_utils import (
    atomic_move,
    atomic_write_text,
    ensure_unique_path,
    is_ignored_file,
    is_supported_audio,
    sha256_file,
    wait_for_stability,
)
from .manifest import Manifest, utc_now
from .outputs import write_outputs
from .transcribers.base import Transcriber, TranscriptionResult
from .transcribers.faster_whisper_transcriber import FasterWhisperTranscriber
from .transcribers.gemini_transcriber import GeminiTranscriber

TranscriberFactory = Callable[[AudioTxtConfig], Transcriber]


class AudioTxtPipeline:
    def __init__(
        self,
        config: AudioTxtConfig,
        *,
        transcriber_factory: TranscriberFactory | None = None,
        logger: logging.Logger | None = None,
    ):
        self.config = config
        self.manifest = Manifest(config.manifest_path)
        self._transcriber_factory = transcriber_factory
        self._transcriber: Transcriber | None = None
        self.logger = logger or create_logger(config)

    def initialize_folders(self) -> None:
        for key in (
            "input_dir",
            "processing_dir",
            "transcripts_dir",
            "processed_dir",
            "failed_dir",
            "logs_dir",
        ):
            folder = self.config.path(key)
            folder.mkdir(parents=True, exist_ok=True)
            gitkeep = folder / ".gitkeep"
            if not gitkeep.exists() and not any(folder.iterdir()):
                gitkeep.write_text("", encoding="utf-8")

    def recover_processing(self) -> list[Path]:
        recovered: list[Path] = []
        processing_dir = self.config.path("processing_dir")
        input_dir = self.config.path("input_dir")
        if not processing_dir.exists():
            return recovered
        for path in sorted(processing_dir.iterdir()):
            if is_ignored_file(path):
                continue
            destination = ensure_unique_path(input_dir / path.name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            recovered_path = Path(shutil.move(str(path), str(destination)))
            recovered.append(recovered_path)
            self.logger.warning("RECOVER moved stranded processing file back to input: %s", recovered_path)
        return recovered

    def run_once(self, *, file_path: Path | None = None, dry_run: bool = False) -> dict[str, int]:
        self.initialize_folders()
        self.recover_processing()

        selected_path: Path | None = None
        if file_path is not None:
            selected_path = (
                self._validate_audio_file(file_path)
                if dry_run
                else self._ingest_external_file(file_path)
            )

        self._log_unsupported_inputs()
        candidates = [selected_path] if selected_path is not None else self.scan_input()
        if dry_run:
            for candidate in candidates:
                print(f"WOULD_PROCESS {candidate}")
            return {"processed": 0, "failed": 0, "duplicates": 0, "candidates": len(candidates)}

        stats = {"processed": 0, "failed": 0, "duplicates": 0, "candidates": len(candidates)}
        for candidate in candidates:
            outcome = self.process_file(candidate)
            if outcome in stats:
                stats[outcome] += 1
        return stats

    def scan_input(self) -> list[Path]:
        input_dir = self.config.path("input_dir")
        extensions = self.config.supported_extensions
        if not input_dir.exists():
            return []
        return sorted(
            path for path in input_dir.iterdir() if is_supported_audio(path, extensions)
        )

    def process_file(self, input_path: Path) -> str:
        settle_seconds = float(self.config.data["audio"]["file_settle_seconds"])
        if not wait_for_stability(input_path, settle_seconds):
            self.logger.info("WAITING file still changing: %s", input_path)
            return "candidates"

        audio_hash: str | None = None
        processing_path: Path | None = None
        try:
            audio_hash = sha256_file(input_path)
            if self.config.data["duplicates"].get("enabled", True) and self.manifest.has_success(audio_hash):
                duplicate_dir = self.config.path("processed_dir") / "duplicates"
                duplicate_path = atomic_move(input_path, duplicate_dir / input_path.name)
                self.manifest.record_duplicate(
                    source_path=input_path, duplicate_path=duplicate_path, audio_hash=audio_hash
                )
                self.logger.info("SKIP duplicate already processed: %s sha256=%s", input_path.name, audio_hash)
                return "duplicates"

            processing_path = atomic_move(input_path, self.config.path("processing_dir") / input_path.name)
            result = self._transcribe(processing_path)
            transcript_paths = write_outputs(
                result,
                source_path=processing_path,
                config=self.config,
                audio_hash=audio_hash,
            )
            processed_path = atomic_move(processing_path, self.config.path("processed_dir") / processing_path.name)
            self.manifest.record_success(
                source_path=input_path,
                processed_path=processed_path,
                transcript_paths=transcript_paths,
                audio_hash=audio_hash,
                engine=result.engine,
                model=result.model,
            )
            self.logger.info("DONE transcribed: %s", processed_path)
            return "processed"
        except Exception as exc:
            self._handle_failure(
                original_path=input_path,
                processing_path=processing_path,
                audio_hash=audio_hash,
                exc=exc,
            )
            return "failed"

    def _ingest_external_file(self, source: Path) -> Path:
        source = self._validate_audio_file(source)
        input_dir = self.config.path("input_dir").resolve()
        if source.parent == input_dir:
            return source
        destination = ensure_unique_path(input_dir / source.name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        self.logger.info("INGEST copied source file into input: %s", destination)
        return destination

    def _validate_audio_file(self, source: Path) -> Path:
        source = source.expanduser().resolve()
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"Audio file does not exist: {source}")
        if not is_supported_audio(source, self.config.supported_extensions):
            raise ValueError(f"Unsupported audio extension: {source}")
        return source

    def _log_unsupported_inputs(self) -> None:
        input_dir = self.config.path("input_dir")
        if not input_dir.exists():
            return
        for path in sorted(input_dir.iterdir()):
            if path.is_file() and not is_ignored_file(path) and path.suffix.lower() not in self.config.supported_extensions:
                self.logger.info("SKIP unsupported extension: %s", path)

    def _transcribe(self, audio_path: Path) -> TranscriptionResult:
        mode = str(self.config.data["engine"].get("mode", "local"))
        if mode == "gemini":
            return GeminiTranscriber(self.config).transcribe(audio_path)

        local_transcriber = self._get_local_transcriber()
        try:
            result = local_transcriber.transcribe(audio_path)
        except Exception:
            if mode == "local_with_gemini_fallback" and self.config.data["gemini"].get("enabled", False):
                self.logger.warning("LOCAL failed; attempting Gemini fallback for %s", audio_path)
                return GeminiTranscriber(self.config).transcribe(audio_path)
            raise

        if (
            mode == "local_with_gemini_fallback"
            and self.config.data["gemini"].get("enabled", False)
            and any(flag in {"low_language_probability", "high_no_speech_probability"} for flag in result.quality_flags)
        ):
            self.logger.warning("LOCAL quality flags triggered Gemini fallback for %s", audio_path)
            return GeminiTranscriber(self.config).transcribe(audio_path)
        return result

    def _get_local_transcriber(self) -> Transcriber:
        if self._transcriber is None:
            if self._transcriber_factory is not None:
                self._transcriber = self._transcriber_factory(self.config)
            else:
                self._transcriber = FasterWhisperTranscriber(self.config)
        return self._transcriber

    def reset_transcriber(self) -> None:
        self._transcriber = None

    def _handle_failure(
        self,
        *,
        original_path: Path,
        processing_path: Path | None,
        audio_hash: str | None,
        exc: Exception,
    ) -> None:
        failed_dir = self.config.path("failed_dir")
        source_for_error = processing_path if processing_path and processing_path.exists() else original_path
        error_path = failed_dir / f"{source_for_error.stem}.error.txt"
        error_text = "\n".join(
            [
                f"timestamp: {utc_now()}",
                f"source path: {source_for_error}",
                f"model: {self.config.data['local']['model_size']}",
                f"engine: {self.config.data['engine']['mode']}",
                f"exception type: {type(exc).__name__}",
                f"exception message: {exc}",
                "",
                traceback.format_exc(),
            ]
        )
        atomic_write_text(error_path, error_text)
        failed_path: Path | None = None
        if source_for_error.exists():
            failed_path = atomic_move(source_for_error, failed_dir / source_for_error.name)
        self.manifest.record_failure(
            source_path=original_path,
            failed_path=failed_path,
            error_path=error_path,
            audio_hash=audio_hash,
            engine=str(self.config.data["engine"].get("mode", "local")),
            model=str(self.config.data["local"].get("model_size", "")),
            exception_type=type(exc).__name__,
            exception_message=str(exc),
        )
        self.logger.error("FAIL transcribing %s: %s", original_path, exc)


def create_logger(config: AudioTxtConfig) -> logging.Logger:
    logger = logging.getLogger(f"audiotxt.{id(config)}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:
        return logger

    logs_dir = config.path("logs_dir")
    logs_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_handler = logging.FileHandler(logs_dir / "audiotxt.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger
