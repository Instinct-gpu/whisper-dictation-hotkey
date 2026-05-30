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

## Configuration

Edit `config.json`:

```json
{
  "hotkey": "<ctrl>+<shift>+space",
  "cancel_key": "esc",
  "model_size": "base.en",
  "device": "cuda",
  "compute_type": "float16",
  "language": "en",
  "paste_method": "clipboard",
  "restore_clipboard": false,
  "sample_rate": 16000,
  "silence_trim": true,
  "visual_indicator": true
}
```

Recommended model sizes:

- `base.en`: quick and good enough for short dictation.
- `small.en`: better accuracy, slower.
- `medium.en`: strong accuracy, much slower on CPU.

The default tries GPU mode (`device: cuda`, `compute_type: float16`) for faster transcription. If GPU model loading fails, the app logs the error and falls back to CPU mode (`device: cpu`, `compute_type: int8`). You can also switch modes from the tray menu; the choice is saved to `config.json` and reused after restart.

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

## Linux/X11 Support

An experimental Linux/X11 version lives in [linux_x11](linux_x11). It is intended for X11 desktop sessions on Debian, Ubuntu, Linux Mint, XFCE, Cinnamon, MATE, KDE on X11, and GNOME when logged into an Xorg session.

It is not tested on this Windows development machine, and it is not designed for Wayland yet. Wayland generally restricts global hotkeys, focus control, and synthetic paste events unless desktop portals or compositor-specific APIs are used.

The X11 app has the same basic shape:

- Hold `Ctrl+Shift+Space` to record.
- Release to transcribe.
- Copy and paste via the X11 clipboard/`xdotool`.
- Save daily transcript logs.
- Show a small recording overlay.

## License

MIT
