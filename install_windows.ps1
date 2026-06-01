$ErrorActionPreference = "Stop"

$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceApp = Join-Path $PackageRoot "app\WhisperDictation"
$SourceAssets = Join-Path $PackageRoot "assets"
$SourceConfig = Join-Path $PackageRoot "config.json"
$SourceEnvExample = Join-Path $PackageRoot ".env.example"
$InstallRoot = Join-Path $env:LOCALAPPDATA "WhisperDictation"
$InstallApp = Join-Path $InstallRoot "app\WhisperDictation"
$Exe = Join-Path $InstallApp "WhisperDictation.exe"
$ShortcutIcon = Join-Path $InstallRoot "assets\whisper-dictation.ico"

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
if (Test-Path $SourceAssets) {
    if (Test-Path (Join-Path $InstallRoot "assets")) {
        Remove-Item -LiteralPath (Join-Path $InstallRoot "assets") -Recurse -Force
    }
    Copy-Item -LiteralPath $SourceAssets -Destination $InstallRoot -Recurse
}

if ((Test-Path $SourceConfig) -and -not (Test-Path (Join-Path $InstallRoot "config.json"))) {
    Copy-Item -LiteralPath $SourceConfig -Destination (Join-Path $InstallRoot "config.json")
}

if (Test-Path $SourceEnvExample) {
    Copy-Item -LiteralPath $SourceEnvExample -Destination (Join-Path $InstallRoot ".env.example") -Force
    if (-not (Test-Path (Join-Path $InstallRoot ".env"))) {
        Copy-Item -LiteralPath $SourceEnvExample -Destination (Join-Path $InstallRoot ".env")
    }
}

$Shell = New-Object -ComObject WScript.Shell
$Startup = [Environment]::GetFolderPath("Startup")
$Programs = [Environment]::GetFolderPath("Programs")
$StartMenuDir = Join-Path $Programs "Relay"
$OldStartupShortcut = Join-Path $Startup "Whisper Dictation.lnk"
$OldStartMenuDir = Join-Path $Programs "Whisper Dictation"
if (Test-Path $OldStartupShortcut) {
    Remove-Item -LiteralPath $OldStartupShortcut -Force
}
if (Test-Path $OldStartMenuDir) {
    Remove-Item -LiteralPath $OldStartMenuDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null

$ShortcutSpecs = @(
    @{ Path = (Join-Path $Startup "Relay.lnk"); Description = "Start Relay automatically" },
    @{ Path = (Join-Path $StartMenuDir "Relay.lnk"); Description = "Launch Relay" }
)

foreach ($Spec in $ShortcutSpecs) {
    $Shortcut = $Shell.CreateShortcut($Spec.Path)
    $Shortcut.TargetPath = $Exe
    $Shortcut.WorkingDirectory = $InstallRoot
    $Shortcut.IconLocation = if (Test-Path $ShortcutIcon) { $ShortcutIcon } else { "$Exe,0" }
    $Shortcut.Description = $Spec.Description
    $Shortcut.Save()
}

Start-Process -FilePath $Exe -WorkingDirectory $InstallRoot -WindowStyle Hidden

Write-Host "Relay installed to $InstallRoot"
Write-Host "It will start automatically when Windows starts."
