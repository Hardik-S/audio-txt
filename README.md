# AudioTxt

AudioTxt is a Windows-friendly, local-first audio transcription tool. Drop audio files into `input_audio/`, run a command, and get `.txt`, `.json`, and optional `.srt` transcript files in `transcripts/`.

The default pipeline uses `faster-whisper` locally:

```yaml
model_size: small.en
device: cpu
compute_type: int8
language: en
```

Gemini is scaffolded as an optional fallback, but it is disabled by default. No API key is required for the MVP.

## Setup

From this folder:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

If Python 3.11 is not installed, use any Python `>=3.10`.

## Initialize Folders

```powershell
python -m audiotxt init
```

This creates any missing runtime folders:

```text
input_audio/
processing/
transcripts/
processed_audio/
failed_audio/
logs/
```

## Process Audio Once

Drop `.wav`, `.mp3`, `.m4a`, `.aac`, `.flac`, or `.ogg` files into `input_audio/`, then run:

```powershell
python -m audiotxt transcribe
```

Successful source files move to `processed_audio/`. Failed source files move to `failed_audio/` with a matching `.error.txt` file. Logs and duplicate history are written under `logs/`.

## Process One File

```powershell
python -m audiotxt transcribe --file "C:\path\to\audio.wav"
```

AudioTxt copies the file into the pipeline, transcribes it, and leaves the original file untouched.

## Watch Mode

```powershell
python -m audiotxt watch
```

Watch mode polls `input_audio/` every five seconds by default.

## Desktop GUI

Open the local desktop interface:

```powershell
python -m audiotxt gui
```

The GUI gives you a minimal control surface for choosing one audio file, processing the queue, starting or stopping folder watch mode, changing the model, switching English vs auto language mode, choosing output formats, opening output folders, and opening recent transcripts. It uses the same local pipeline and config as the CLI. `Stop Watch` stops the polling loop after the active cycle finishes; an active transcription is allowed to finish so files are not corrupted.

## Dry Run

```powershell
python -m audiotxt transcribe --dry-run
```

Dry run prints the files that would be processed without moving or transcribing them.

## Accuracy Modes

Use the default for most English audio:

```powershell
python -m audiotxt transcribe --model small.en
```

Use `medium.en` when accuracy matters more than speed:

```powershell
python -m audiotxt transcribe --model medium.en
```

For language auto-detection, set this in `config.yaml`:

```yaml
local:
  model_size: "small"
  language: null
```

If `language: null` is used with an English-only model such as `small.en`, AudioTxt switches to the multilingual equivalent, such as `small`, and logs a warning.

## Windows Spoken-WAV Smoke Test

Generate a small spoken WAV:

```powershell
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SetOutputToWaveFile("input_audio\hello.wav")
$s.Speak("Hello, this is a smoke test for local transcription.")
$s.Dispose()
```

Then run:

```powershell
python -m audiotxt transcribe
```

The transcript should roughly contain:

```text
Hello, this is a smoke test for local transcription.
```

## Developer Checks

Run unit tests without downloading a Whisper model:

```powershell
python -m pip install -e ".[test]"
python -m pytest
```

Run the pipeline smoke test with a fake transcriber:

```powershell
python tests\smoke_test.py
```

## Known Limitations

- The first real transcription run downloads the configured Whisper model.
- CPU transcription can be slow on long files; use `base.en` for speed or `medium.en` for accuracy.
- Speaker labels, diarization, word-level timestamps, and live transcription are intentionally out of scope for the MVP.
- Gemini fallback uploads audio to a cloud API and is disabled unless explicitly configured.
