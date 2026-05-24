from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from .config import load_config
from .pipeline import AudioTxtPipeline

MODELS = ("base.en", "small.en", "medium.en", "small")


class GuiController:
    def __init__(
        self,
        config_path: Path,
        *,
        model_override: str | None = None,
        event_sink: Callable[[str], None] | None = None,
    ):
        self.config_path = config_path
        self.event_sink = event_sink or (lambda _message: None)
        self.config = load_config(config_path, model_override=model_override)
        self.pipeline = AudioTxtPipeline(self.config)
        self.stop_event = threading.Event()
        self.pipeline_lock = threading.Lock()
        self._transcriber_settings = self._current_transcriber_settings()

    def apply_settings(
        self,
        *,
        model: str,
        language_mode: str,
        txt: bool,
        json_output: bool,
        srt: bool,
        cleaned_txt: bool,
    ) -> None:
        model = model.strip()
        if not model:
            raise ValueError("Model cannot be blank.")
        if not any((txt, json_output, srt, cleaned_txt)):
            raise ValueError("Choose at least one output format.")
        language = None if language_mode == "Auto" else "en"
        if language is None and model.endswith(".en"):
            multilingual = model.removesuffix(".en")
            self.event_sink(f"Auto language uses multilingual model: {model} -> {multilingual}")
            model = multilingual
        self.config.data["local"]["model_size"] = model
        self.config.data["local"]["language"] = language
        self.config.data["outputs"]["txt"] = txt
        self.config.data["outputs"]["json"] = json_output
        self.config.data["outputs"]["srt"] = srt
        self.config.data["outputs"]["cleaned_txt"] = cleaned_txt
        next_settings = self._current_transcriber_settings()
        if next_settings != self._transcriber_settings:
            self.pipeline.reset_transcriber()
            self._transcriber_settings = next_settings

    def initialize(self) -> dict[str, int]:
        with self.pipeline_lock:
            self.pipeline.initialize_folders()
        for warning in self.config.warnings:
            self.event_sink(f"Warning: {warning}")
        self.event_sink("Folders ready.")
        return {"processed": 0, "failed": 0, "duplicates": 0, "candidates": 0}

    def process_queue(self) -> dict[str, int]:
        self.event_sink("Processing queued audio...")
        with self.pipeline_lock:
            stats = self.pipeline.run_once()
        self.event_sink(format_stats("Queue complete", stats))
        return stats

    def process_file(self, path: Path) -> dict[str, int]:
        self.event_sink(f"Processing {path.name}...")
        with self.pipeline_lock:
            stats = self.pipeline.run_once(file_path=path)
        self.event_sink(format_stats(path.name, stats))
        return stats

    def watch_loop(self, poll_seconds: float | None = None) -> None:
        self.stop_event.clear()
        interval = poll_seconds or float(self.config.data["watch"]["poll_seconds"])
        self.event_sink("Watch folder started.")
        try:
            while not self.stop_event.is_set():
                with self.pipeline_lock:
                    stats = self.pipeline.run_once()
                if stats["processed"] or stats["failed"] or stats["duplicates"]:
                    self.event_sink(format_stats("Watch cycle", stats))
                self.stop_event.wait(interval)
        except Exception as exc:
            self.event_sink(f"Watch error: {exc}")
        finally:
            self.event_sink("Watch folder stopped.")
            self.event_sink("__status__:Ready")

    def stop_watch(self) -> None:
        self.stop_event.set()

    def recent_transcripts(self, limit: int = 20) -> list[Path]:
        transcripts_dir = self.config.path("transcripts_dir")
        if not transcripts_dir.exists():
            return []
        files = [
            path
            for path in transcripts_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".txt", ".json", ".srt"}
        ]
        return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)[:limit]

    def folder(self, key: str) -> Path:
        with self.pipeline_lock:
            self.pipeline.initialize_folders()
        return self.config.path(key)

    def _current_transcriber_settings(self) -> tuple[str, str, str, str, str, int, bool, bool]:
        local = self.config.data["local"]
        return (
            str(local.get("provider", "faster-whisper")),
            str(local.get("model_size", "")),
            str(local.get("device", "")),
            str(local.get("compute_type", "")),
            str(local.get("language", "")),
            int(local.get("beam_size", 5)),
            bool(local.get("vad_filter", True)),
            bool(local.get("condition_on_previous_text", False)),
        )


def format_stats(label: str, stats: dict[str, int]) -> str:
    return (
        f"{label}: processed {stats['processed']}, failed {stats['failed']}, "
        f"duplicates {stats['duplicates']}, candidates {stats['candidates']}"
    )


class AudioTxtApp:
    def __init__(self, root: tk.Tk, config_path: Path):
        self.root = root
        self.events: queue.Queue[str] = queue.Queue()
        self.controller = GuiController(config_path, event_sink=self.events.put)
        self.worker: threading.Thread | None = None
        self.watch_thread: threading.Thread | None = None

        self.model_var = tk.StringVar(value=str(self.controller.config.data["local"]["model_size"]))
        self.language_var = tk.StringVar(
            value="Auto" if self.controller.config.data["local"].get("language") is None else "English"
        )
        self.txt_var = tk.BooleanVar(value=bool(self.controller.config.data["outputs"]["txt"]))
        self.json_var = tk.BooleanVar(value=bool(self.controller.config.data["outputs"]["json"]))
        self.srt_var = tk.BooleanVar(value=bool(self.controller.config.data["outputs"]["srt"]))
        self.cleaned_var = tk.BooleanVar(value=bool(self.controller.config.data["outputs"]["cleaned_txt"]))
        self.status_var = tk.StringVar(value="Ready")
        self.current_var = tk.StringVar(value="Drop files into input_audio, or choose a file.")
        self.selected_transcript: Path | None = None

        self._configure_window()
        self._build_layout()
        self._run_worker("init", self.controller.initialize)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._poll_events()

    def _configure_window(self) -> None:
        self.root.title("AudioTxt")
        self.root.geometry("980x680")
        self.root.minsize(860, 600)
        self.root.configure(bg="#f5f5f7")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background="#f5f5f7", foreground="#1d1d1f")
        style.configure("Title.TLabel", font=("Segoe UI", 24, "bold"), background="#f5f5f7")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10), foreground="#6e6e73", background="#f5f5f7")
        style.configure("Panel.TFrame", background="#ffffff", relief="flat")
        style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"), background="#ffffff")
        style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"), background="#f5f5f7")
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(16, 10))
        style.configure("TButton", padding=(12, 8))
        style.configure("TCheckbutton", background="#ffffff")
        style.configure("TRadiobutton", background="#ffffff")
        style.configure("TCombobox", padding=(8, 6))

    def _build_layout(self) -> None:
        shell = ttk.Frame(self.root, padding=24)
        shell.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(shell)
        header.pack(fill=tk.X, pady=(0, 18))
        ttk.Label(header, text="AudioTxt", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, textvariable=self.status_var, style="Status.TLabel").pack(side=tk.RIGHT, pady=10)
        ttk.Label(
            shell,
            text="Local transcription, folder watching, and clean transcript handoff.",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(0, 18))

        main = ttk.Frame(shell)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=1)

        left = self._panel(main)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        right = self._panel(main)
        right.grid(row=0, column=1, sticky="nsew")

        self._build_actions(left)
        self._build_settings(left)
        self._build_activity(left)
        self._build_results(right)
        self._build_folders(right)

    def _panel(self, parent: ttk.Frame) -> ttk.Frame:
        return ttk.Frame(parent, style="Panel.TFrame", padding=18)

    def _build_actions(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Start", style="Section.TLabel").pack(anchor=tk.W)
        actions = ttk.Frame(parent, style="Panel.TFrame")
        actions.pack(fill=tk.X, pady=(10, 18))
        ttk.Button(actions, text="Choose Audio", style="Primary.TButton", command=self._choose_audio).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(actions, text="Process Queue", command=self._process_queue).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(actions, text="Watch Folder", command=self._start_watch).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(actions, text="Stop Watch", command=self._stop_watch).pack(side=tk.LEFT)
        ttk.Label(parent, textvariable=self.current_var, style="Subtitle.TLabel").pack(anchor=tk.W)

    def _build_settings(self, parent: ttk.Frame) -> None:
        ttk.Separator(parent).pack(fill=tk.X, pady=18)
        ttk.Label(parent, text="Settings", style="Section.TLabel").pack(anchor=tk.W)
        grid = ttk.Frame(parent, style="Panel.TFrame")
        grid.pack(fill=tk.X, pady=(10, 6))
        grid.columnconfigure(1, weight=1)

        ttk.Label(grid, text="Model", background="#ffffff").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        model = ttk.Combobox(grid, textvariable=self.model_var, values=MODELS, state="readonly")
        model.grid(row=0, column=1, sticky="ew")

        ttk.Label(grid, text="Language", background="#ffffff").grid(
            row=1, column=0, sticky=tk.W, padx=(0, 10), pady=10
        )
        language = ttk.Frame(grid, style="Panel.TFrame")
        language.grid(row=1, column=1, sticky=tk.W, pady=10)
        ttk.Radiobutton(language, text="English", value="English", variable=self.language_var).pack(side=tk.LEFT)
        ttk.Radiobutton(language, text="Auto", value="Auto", variable=self.language_var).pack(side=tk.LEFT, padx=(14, 0))

        outputs = ttk.Frame(parent, style="Panel.TFrame")
        outputs.pack(fill=tk.X, pady=(8, 0))
        ttk.Checkbutton(outputs, text="TXT", variable=self.txt_var).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(outputs, text="JSON", variable=self.json_var).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(outputs, text="SRT", variable=self.srt_var).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(outputs, text="Cleaned TXT", variable=self.cleaned_var).pack(side=tk.LEFT)

    def _build_activity(self, parent: ttk.Frame) -> None:
        ttk.Separator(parent).pack(fill=tk.X, pady=18)
        ttk.Label(parent, text="Activity", style="Section.TLabel").pack(anchor=tk.W)
        self.log = tk.Text(
            parent,
            height=12,
            relief=tk.FLAT,
            bg="#f5f5f7",
            fg="#1d1d1f",
            insertbackground="#1d1d1f",
            padx=12,
            pady=12,
            wrap=tk.WORD,
        )
        self.log.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.log.configure(state=tk.DISABLED)

    def _build_results(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Recent Transcripts", style="Section.TLabel").pack(anchor=tk.W)
        self.results = tk.Listbox(
            parent,
            height=14,
            relief=tk.FLAT,
            bg="#f5f5f7",
            fg="#1d1d1f",
            selectbackground="#007aff",
            selectforeground="#ffffff",
            activestyle="none",
            highlightthickness=0,
        )
        self.results.pack(fill=tk.BOTH, expand=True, pady=(10, 10))
        self.results.bind("<<ListboxSelect>>", self._select_transcript)

        buttons = ttk.Frame(parent, style="Panel.TFrame")
        buttons.pack(fill=tk.X, pady=(0, 18))
        ttk.Button(buttons, text="Open Transcript", command=self._open_transcript).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Open Folder", command=lambda: self._open_folder("transcripts_dir")).pack(side=tk.LEFT)
        self._refresh_results()

    def _build_folders(self, parent: ttk.Frame) -> None:
        ttk.Separator(parent).pack(fill=tk.X, pady=10)
        ttk.Label(parent, text="Folders", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 10))
        for label, key in (
            ("Input", "input_dir"),
            ("Processed", "processed_dir"),
            ("Failed", "failed_dir"),
            ("Logs", "logs_dir"),
        ):
            ttk.Button(parent, text=label, command=lambda folder_key=key: self._open_folder(folder_key)).pack(
                fill=tk.X, pady=3
            )

    def _apply_settings(self) -> None:
        self.controller.apply_settings(
            model=self.model_var.get(),
            language_mode=self.language_var.get(),
            txt=self.txt_var.get(),
            json_output=self.json_var.get(),
            srt=self.srt_var.get(),
            cleaned_txt=self.cleaned_var.get(),
        )
        self.model_var.set(str(self.controller.config.data["local"]["model_size"]))

    def _choose_audio(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose audio",
            filetypes=[
                ("Audio files", "*.wav *.mp3 *.m4a *.aac *.flac *.ogg"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._run_worker("file", lambda: self._process_selected_file(Path(path)))

    def _process_selected_file(self, path: Path) -> dict[str, int]:
        self._apply_settings()
        return self.controller.process_file(path)

    def _process_queue(self) -> None:
        self._run_worker("queue", self._process_queue_now)

    def _process_queue_now(self) -> dict[str, int]:
        self._apply_settings()
        return self.controller.process_queue()

    def _start_watch(self) -> None:
        if self.watch_thread and self.watch_thread.is_alive():
            self.events.put("Watch folder is already running.")
            return
        if self.worker and self.worker.is_alive():
            self.events.put("Wait for the current transcription job before starting watch mode.")
            return
        self._apply_settings()
        self.status_var.set("Watching")
        self.watch_thread = threading.Thread(target=self.controller.watch_loop, daemon=True)
        self.watch_thread.start()

    def _stop_watch(self) -> None:
        self.controller.stop_watch()
        self.status_var.set("Ready")

    def _run_worker(self, label: str, action: Callable[[], object]) -> None:
        if self.worker and self.worker.is_alive():
            self.events.put("A transcription job is already running.")
            return
        if self.watch_thread and self.watch_thread.is_alive():
            self.events.put("Stop Watch before starting a manual transcription job.")
            return

        def run() -> None:
            self.events.put("__status__:Working")
            try:
                action()
            except Exception as exc:
                self.events.put(f"Error: {exc}")
            finally:
                if not (self.watch_thread and self.watch_thread.is_alive()):
                    self.events.put("__status__:Ready")
                self.events.put("__refresh__")

        self.worker = threading.Thread(target=run, name=f"audiotxt-gui-{label}", daemon=True)
        self.worker.start()

    def _poll_events(self) -> None:
        try:
            while True:
                message = self.events.get_nowait()
                if message == "__refresh__":
                    self._refresh_results()
                elif message.startswith("__status__:"):
                    self.status_var.set(message.split(":", 1)[1])
                else:
                    self._append_log(message)
        except queue.Empty:
            pass
        self.root.after(150, self._poll_events)

    def _append_log(self, message: str) -> None:
        self.current_var.set(message)
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, f"{time.strftime('%H:%M:%S')}  {message}\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _refresh_results(self) -> None:
        self.results.delete(0, tk.END)
        self.selected_transcript = None
        for path in self.controller.recent_transcripts():
            self.results.insert(tk.END, path.name)

    def _select_transcript(self, _event: object) -> None:
        selection = self.results.curselection()
        transcripts = self.controller.recent_transcripts()
        if selection and selection[0] < len(transcripts):
            self.selected_transcript = transcripts[selection[0]]

    def _open_transcript(self) -> None:
        if self.selected_transcript is None:
            messagebox.showinfo("AudioTxt", "Select a transcript first.")
            return
        open_path(self.selected_transcript)

    def _open_folder(self, key: str) -> None:
        open_path(self.controller.folder(key))

    def _close(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("AudioTxt", "A transcription is still running. Wait for it to finish before closing.")
            return
        self.controller.stop_watch()
        self.root.destroy()


def open_path(path: Path) -> None:
    path = path.resolve()
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
        return
    subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


def launch_gui(config_path: Path) -> int:
    root = tk.Tk()
    AudioTxtApp(root, config_path)
    root.mainloop()
    return 0
