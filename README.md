# Whisper Dictation Hotkey

A small Windows background dictation app: hold a keyboard shortcut, speak, release, and the transcribed text is pasted into the currently focused input.

It uses local Whisper transcription through `faster-whisper`, so recordings are processed on your PC rather than sent to a cloud service.

## Features

- Hold-to-record global hotkey
- Local speech-to-text with Whisper
- Automatic paste into the active text field
- Small recording overlay with animated waveform
- Daily transcript history logs
- Tray icon with quick access to logs
- Windows Startup and Start Menu shortcut support
- GPU/CPU mode switching from the tray menu
- Optional local AI cleanup with Ollama

## Supported Platforms

Tested target:

- Windows 11

Expected to work:

- Windows 10

The app uses standard Windows APIs for global key detection, foreground window restore, clipboard paste, tray icon, and Startup shortcuts. Windows 11 rounded-corner hints are best-effort; on Windows 10 the overlay should still work, just without native Windows 11 corner styling.

## Default Shortcut

Default hotkey: `Ctrl+Shift+Space`

- Hold `Ctrl+Shift+Space` to record.
- Release any part of the shortcut to stop, transcribe, save the transcript, and paste.
- Press `Esc` while recording to cancel.

If the shortcut conflicts with another app, edit `config.json`.

## Quick Start From Source

Install Python 3.10 or newer, then run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\python.exe .\whisper_dictation.py
```

The first transcription downloads the configured Whisper model. After that, transcription runs locally.

## Easy Windows Install

For normal users, use the latest release ZIP from GitHub Releases:

1. Download `WhisperDictation-Windows.zip`.
2. Extract the ZIP.
3. Right-click `install_windows.ps1` and choose **Run with PowerShell**.
4. Hold `Ctrl+Shift+Space` to dictate.

Optional local cleanup:

- Install Ollama from [ollama.com/download](https://ollama.com/download).
- Keep Whisper Dictation in `Clean` or `Enhanced` mode.
- On first cleanup use, Whisper Dictation automatically downloads `qwen2.5:1.5b` through Ollama.

The installer copies the app to:

```text
%LOCALAPPDATA%\WhisperDictation
```

It also creates:

- A Start Menu shortcut named `Whisper Dictation`
- A Startup shortcut so the app starts when Windows starts

To remove it, run:

```powershell
.\uninstall_windows.ps1
```

## Packaged Windows App

If you build the packaged app, the executable is:

```text
app\WhisperDictation\WhisperDictation.exe
```

To build it, see [BUILDING.md](BUILDING.md).

After building, install Startup and Start Menu shortcuts:

```powershell
.\scripts\install_startup_shortcuts.ps1
```

You can also run:

```powershell
.\run.ps1
```

`run.ps1` launches the packaged app when it exists, and otherwise falls back to running from source.

## Logs

Each successful transcription is saved to a daily text file:

```text
log\YYYY-MM-DD.txt
```

Entries look like this:

```text
[12:05:10] dictated text here
```

Empty log files are not created. This is useful if text is pasted into the wrong place or an input field was not focused.

If cleanup is enabled, history keeps both the raw transcript and the cleaned output when they differ.

## Configuration

Edit `config.json`:

```json
{
  "hotkey": "<ctrl>+<shift>+space",
  "cancel_key": "esc",
  "model_size": "base.en",
  "device": "cpu",
  "compute_type": "int8",
  "language": "en",
  "paste_method": "clipboard",
  "restore_clipboard": false,
  "sample_rate": 16000,
  "silence_trim": true,
  "visual_indicator": true,
  "cleanup_mode": "clean",
  "cleanup_engine": "ollama",
  "ollama_model": "qwen2.5:1.5b",
  "ollama_base_url": "http://localhost:11434"
}
```

Recommended model sizes:

- `base.en`: quick and good enough for short dictation.
- `small.en`: better accuracy, slower.
- `medium.en`: strong accuracy, much slower on CPU.

The default uses CPU mode (`device: cpu`, `compute_type: int8`) because it works on the widest range of Windows 10 and Windows 11 PCs. You can switch to GPU mode from the tray menu if your machine supports CUDA; the choice is saved to `config.json` and reused after restart. GPU mode is primarily for NVIDIA CUDA setups and may not work automatically on AMD, Intel, or unsupported laptop GPUs.

Cleanup modes:

- `raw`: paste Whisper's transcript directly.
- `clean`: fix punctuation/casing and remove filler words while preserving meaning.
- `enhanced`: more opinionated rewrite for clearer polished text.

Cleanup requires Ollama when `cleanup_engine` is `ollama`. If Ollama is not running, the app prompts once and falls back to raw dictation. If Ollama is running but the configured model is missing, the app pulls it automatically the first time cleanup is used.

## Troubleshooting

If nothing pastes:

- Check whether the target input field was focused before recording.
- Try a normal text editor first, such as Notepad.
- Check `whisper_dictation.log` for errors.
- Check `log\YYYY-MM-DD.txt` to see whether transcription succeeded.

If global hotkeys do not work in an elevated app:

- Run Whisper Dictation as Administrator too. Windows may block lower-privilege apps from sending keys into elevated windows.

If the first transcription is slow:

- The first run may download the Whisper model and initialize the transcription engine.

If cleanup is slow the first time:

- Ollama may be downloading `qwen2.5:1.5b`.
- Future cleanups are faster once the model is present.

## Linux/X11 Support

An experimental Linux/X11 version lives in [linux_x11](linux_x11). It is intended for X11 desktop sessions on Debian, Ubuntu, Linux Mint, XFCE, Cinnamon, MATE, KDE on X11, and GNOME when logged into an Xorg session.

It is not tested on this Windows development machine, and it is not designed for Wayland yet. Wayland generally restricts global hotkeys, focus control, and synthetic paste events unless desktop portals or compositor-specific APIs are used.

The X11 app has the same basic shape:

- Hold `Ctrl+Shift+Space` to record.
- Release to transcribe.
- Copy and paste via the X11 clipboard/`xdotool`.
- Save daily transcript logs.
- Show a small recording overlay.
- Use the same Ollama cleanup config and automatic `qwen2.5:1.5b` pull.

## License

MIT
