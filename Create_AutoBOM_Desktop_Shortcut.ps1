# Creates a Windows desktop shortcut named "AutoBOM" that points at
# Start_AutoBOM.bat in this checkout, so an operator can start AutoBOM by
# double-clicking a desktop icon instead of navigating to this folder.
#
# Run once per machine/user (from this repository, in PowerShell):
#   powershell -ExecutionPolicy Bypass -File Create_AutoBOM_Desktop_Shortcut.ps1
#
# Does not hardcode a specific user's Desktop path -- [Environment]::GetFolderPath
# resolves the CURRENT user's real Desktop location, including redirected/
# OneDrive-managed desktops.
#
# Useful both for local/operator testing and for whoever operates the
# actual deployment machine (manual start/restart there too). Once
# AutoBOM runs as an always-on Windows service on that machine, ordinary
# TEAM MEMBERS should just bookmark the AutoBOM browser URL instead --
# double-clicking this while the service is already running would start
# a second, conflicting local instance. See the "One-Click Launcher"
# section in README.md.

param(
    [string]$RepoPath = $PSScriptRoot,
    [string]$ShortcutName = "AutoBOM"
)

$ErrorActionPreference = "Stop"

$launcherPath = Join-Path $RepoPath "Start_AutoBOM.bat"
if (-not (Test-Path $launcherPath)) {
    Write-Error "Start_AutoBOM.bat not found at $launcherPath -- run this script from the AutoBOM repository root."
    exit 1
}

$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "$ShortcutName.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcherPath
$shortcut.WorkingDirectory = $RepoPath
$shortcut.Description = "Start AutoBOM (local/operator testing)"
$shortcut.Save()

Write-Host "Created desktop shortcut: $shortcutPath"
Write-Host "Double-click the 'AutoBOM' icon on your Desktop to start AutoBOM."
