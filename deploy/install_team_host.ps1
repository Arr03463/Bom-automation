# LEGACY initial Wi-Fi installation helper. Not appropriate for the Caddy
# deployment: it opens TCP 8502. Use configure_team_boot_task.ps1 for the
# existing task; do not rerun this installer or change the existing firewall.
param(
    [string]$RepoPath = (Split-Path -Parent $PSScriptRoot),
    [string]$HostUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
)
$ErrorActionPreference = 'Stop'
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object System.Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this installer in an Administrator PowerShell window. It adds one scoped firewall rule and a scheduled task.'
}
$RepoPath = $RepoPath.TrimEnd('\')
$pythonExe = Join-Path $RepoPath '.venv\Scripts\python.exe'
$launchScript = Join-Path $RepoPath 'deploy\launch_team.ps1'
if (-not (Test-Path $pythonExe) -or -not (Test-Path $launchScript)) { throw 'AutoBOM installation is incomplete.' }

# Restrict inbound traffic to this Wi-Fi interface and its directly connected subnet.
$ruleName = 'AutoBOM-Team-WiFi-8502'
if (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue) {
    throw "Firewall rule $ruleName already exists. Review it before replacing the installation."
}
if (Get-ScheduledTask -TaskName 'AutoBOM Team Host' -ErrorAction SilentlyContinue) {
    throw 'AutoBOM Team Host task already exists. Review it before replacing the installation.'
}
New-NetFirewallRule -Name $ruleName -DisplayName 'AutoBOM team browsers (Wi-Fi subnet, TCP 8502)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8502 -RemoteAddress LocalSubnet -InterfaceAlias 'Wi-Fi 2' -Profile Any | Out-Null

# Uses the existing signed-in operator account; no password or elevated app process.
# This starts after that user signs in, not before login following a reboot.
$arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -RepoPath "{1}"' -f $launchScript, $RepoPath
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments -WorkingDirectory $RepoPath
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $HostUser
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $HostUser -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'AutoBOM Team Host' -Action $action -Trigger $trigger -Settings $settings -Principal $taskPrincipal -Description 'AutoBOM Wi-Fi browser host; starts when the host operator signs in.' | Out-Null
Start-ScheduledTask -TaskName 'AutoBOM Team Host'
Write-Host 'Installed and started AutoBOM Team Host. Keep the PC awake and the host user signed in.'
