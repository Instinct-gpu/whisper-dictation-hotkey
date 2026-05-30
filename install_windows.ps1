$ErrorActionPreference = "Stop"

$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceApp = Join-Path $PackageRoot "app\WhisperDictation"
$SourceConfig = Join-Path $PackageRoot "config.json"
$InstallRoot = Join-Path $env:LOCALAPPDATA "WhisperDictation"
$InstallApp = Join-Path $InstallRoot "app\WhisperDictation"
$Exe = Join-Path $InstallApp "WhisperDictation.exe"

if (-not (Test-Path $SourceApp)) {
    throw "Packaged app folder not found: $SourceApp"
}

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null

Get-Process WhisperDictation -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like "$InstallRoot*"
} | Stop-Process -Force

if (Test-Path (Join-Path $InstallRoot "app")) {
    Remove-Item -LiteralPath (Join-Path $InstallRoot "app") -Recurse -Force
}

New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot "app") | Out-Null
Copy-Item -LiteralPath $SourceApp -Destination (Join-Path $InstallRoot "app") -Recurse

if ((Test-Path $SourceConfig) -and -not (Test-Path (Join-Path $InstallRoot "config.json"))) {
    Copy-Item -LiteralPath $SourceConfig -Destination (Join-Path $InstallRoot "config.json")
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
    $Shortcut.WorkingDirectory = $InstallRoot
    $Shortcut.IconLocation = "$Exe,0"
    $Shortcut.Description = $Spec.Description
    $Shortcut.Save()
}

Start-Process -FilePath $Exe -WorkingDirectory $InstallRoot -WindowStyle Hidden

Write-Host "Whisper Dictation installed to $InstallRoot"
Write-Host "It will start automatically when Windows starts."

