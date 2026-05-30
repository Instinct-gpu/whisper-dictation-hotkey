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
- CPU-first defaults so it does not fight GPU-heavy workloads

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
  "device": "cpu",
  "compute_type": "int8",
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

The default uses CPU mode (`device: cpu`, `compute_type: int8`) so the app stays responsive even when the GPU is busy with other work.

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

## Linux Support

Linux is not implemented yet. See the notes at the end of this README for what would be needed.

At a high level, the transcription and audio pieces are portable, but these Windows-specific areas need Linux replacements:

- Global hotkey capture
- Active window restore
- Clipboard paste
- Tray icon behavior
- Startup integration
- Overlay focus/no-activation behavior

For Linux, likely building blocks would be `pynput` or desktop-specific hotkey APIs, `xclip`/`wl-copy` for clipboard, `xdotool`/Wayland portals for paste, and autostart `.desktop` files.

## License

MIT
