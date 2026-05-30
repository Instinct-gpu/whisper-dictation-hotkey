$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Exe = Join-Path $Root "app\WhisperDictation\WhisperDictation.exe"

if (-not (Test-Path $Exe)) {
    throw "Packaged app not found: $Exe. Build it first; see BUILDING.md."
}

$Shell = New-Object -ComObject WScript.Shell
$Startup = [Environment]::GetFolderPath("Startup")
$Programs = [Environment]::GetFolderPath("Programs")
$StartMenuDir = Join-Path $Programs "Whisper Dictation"
New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null

$ShortcutSpecs = @(
    @{ Path = (Join-Path $Startup "Whisper Dictation.lnk"); Description = "Start Whisper Dictation automatically" },
    @{ Path = (Join-Path $StartMenuDir "Whisper Dictation.lnk"); Description = "Launch Whisper Dictation" }
)

foreach ($Spec in $ShortcutSpecs) {
    $Shortcut = $Shell.CreateShortcut($Spec.Path)
    $Shortcut.TargetPath = $Exe
    $Shortcut.WorkingDirectory = $Root
    $Shortcut.IconLocation = "$Exe,0"
    $Shortcut.Description = $Spec.Description
    $Shortcut.Save()
}

Write-Host "Installed Startup and Start Menu shortcuts."
