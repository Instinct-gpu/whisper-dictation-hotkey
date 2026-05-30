# Building Whisper Dictation Hotkey

These notes are for building the Windows packaged app from source.

## Requirements

- Windows 10 or Windows 11
- Python 3.10 or newer
- A microphone

## Create A Development Environment

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\pip.exe install pyinstaller==6.11.1
```

## Run From Source

```powershell
.\.venv\Scripts\python.exe .\whisper_dictation.py
```

## Build The Packaged App

Generate the icon:

```powershell
.\.venv\Scripts\python.exe .\scripts\make_icon.py
```

Build the Windows app folder:

```powershell
$Icon = (Resolve-Path .\assets\whisper-dictation.ico).Path
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean --onedir --windowed `
  --name WhisperDictation `
  --icon "$Icon" `
  --distpath .\app `
  --workpath .\build\pyinstaller-onedir `
  --specpath .\build `
  .\whisper_dictation.py
```

The executable will be:

```text
app\WhisperDictation\WhisperDictation.exe
```

## Notes

- The default configuration uses CPU mode (`device: cpu`, `compute_type: int8`) so it does not compete with GPU workloads.
- `vad_filter` is disabled in the current build because PyInstaller packaging did not include faster-whisper's optional Silero VAD assets by default.
- The generated `app`, `build`, `.venv`, `log`, and runtime files are intentionally ignored by git.

