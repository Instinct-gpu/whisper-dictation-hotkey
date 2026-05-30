$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Exe = Join-Path $Root "app\WhisperDictation\WhisperDictation.exe"

if (Test-Path $Exe) {
    Start-Process -FilePath $Exe -WorkingDirectory $Root -WindowStyle Hidden
    exit
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "Virtual environment not found. Creating .venv and installing dependencies..."
    python -m venv (Join-Path $Root ".venv")
    & $Python -m pip install --upgrade pip
    & (Join-Path $Root ".venv\Scripts\pip.exe") install -r (Join-Path $Root "requirements.txt")
}

& $Python (Join-Path $Root "whisper_dictation.py")
