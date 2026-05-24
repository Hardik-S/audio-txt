$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$desktop = [Environment]::GetFolderPath("Desktop")
$pythonw = (Get-Command pythonw.exe -ErrorAction Stop).Source
$shortcutPath = Join-Path $desktop "AudioTxt.lnk"
$iconPath = Join-Path $repo "assets\audiotxt.ico"

if (-not (Test-Path -LiteralPath $iconPath)) {
    throw "Icon file not found: $iconPath"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = "-m audiotxt gui"
$shortcut.WorkingDirectory = $repo
$shortcut.IconLocation = "$iconPath,0"
$shortcut.Description = "Open AudioTxt local transcription GUI"
$shortcut.Save()

Write-Output "Created shortcut: $shortcutPath"
