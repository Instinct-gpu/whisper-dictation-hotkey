# Whisper Dictation Hotkey for Linux/X11

This is an experimental Linux/X11 version of the Windows dictation app.

It is intended for X11 desktop sessions on distributions such as Debian, Ubuntu, Linux Mint, XFCE, Cinnamon, MATE, KDE on X11, and GNOME when logged into an Xorg session.

It is not designed for Wayland yet. Wayland generally restricts global hotkeys, focus control, and synthetic paste events unless desktop portals or compositor-specific APIs are used.

## What Works In Principle

- Hold `Ctrl+Shift+Space` to record.
- Release the shortcut to transcribe.
- Copy transcript to the clipboard.
- Paste into the focused field using `xdotool`.
- Save successful transcripts to daily logs.
- Show a small recording overlay.
- Optionally clean transcripts through local Ollama.

## Requirements

Python dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-linux.txt
```

System packages:

```bash
sudo apt install portaudio19-dev xclip xdotool
```

Depending on your distro, package names may vary.

## Run

From the repository root:

```bash
source .venv/bin/activate
python linux_x11/whisper_dictation_x11.py
```

## Configuration

The script creates and reads:

```text
linux_x11/config.json
```

Default:

```json
{
  "hotkey": "ctrl+shift+space",
  "model_size": "base.en",
  "device": "cpu",
  "compute_type": "int8",
  "language": "en",
  "sample_rate": 16000,
  "cleanup_mode": "clean",
  "cleanup_engine": "ollama",
  "ollama_model": "qwen2.5:1.5b",
  "ollama_base_url": "http://localhost:11434"
}
```

Set `"device": "cuda"` and `"compute_type": "float16"` if the Linux system has a compatible CUDA setup.

Cleanup modes:

- `raw`: paste Whisper's transcript directly.
- `clean`: fix punctuation/casing and remove filler words while preserving meaning.
- `bullets`: turn the transcript into a concise bullet list.
- `enhanced`: more opinionated rewrite for clearer polished text.

Cleanup requires Ollama when `cleanup_engine` is `ollama`. Install Ollama from [ollama.com/download](https://ollama.com/download). If Ollama is running but the configured model is missing, the app pulls `qwen2.5:1.5b` automatically the first time cleanup is used. If Ollama is not running, the script falls back to raw dictation.

## Notes

This file is untested in this repo because the original development machine is Windows-only. The audio and Whisper pieces should be portable; the fragile parts are global keyboard capture and paste automation, which vary by Linux desktop/session.
