$ErrorActionPreference = "Stop"

$InstallRoot = Join-Path $env:LOCALAPPDATA "WhisperDictation"
$StartupShortcut = Join-Path ([Environment]::GetFolderPath("Startup")) "Whisper Dictation.lnk"
$StartMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) "Whisper Dictation"

Get-Process WhisperDictation -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like "$InstallRoot*"
} | Stop-Process -Force

if (Test-Path $StartupShortcut) {
    Remove-Item -LiteralPath $StartupShortcut -Force
}

if (Test-Path $StartMenuDir) {
    Remove-Item -LiteralPath $StartMenuDir -Recurse -Force
}

if (Test-Path $InstallRoot) {
    Remove-Item -LiteralPath $InstallRoot -Recurse -Force
}

Write-Host "Whisper Dictation uninstalled."

