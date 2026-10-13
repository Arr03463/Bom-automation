# MANUAL ADMIN TOOL. Not run automatically by any launcher.
# Changes only the existing AutoBOM task; no firewall or service changes.
param(
    [string]$RepoPath = (Split-Path -Parent $PSScriptRoot),
    [string]$UserName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
)
$ErrorActionPreference = 'Stop'
$principal = New-Object System.Security.Principal.WindowsPrincipal([System.Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run in Administrator PowerShell.' }
$taskName = 'AutoBOM Team Host'
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
if ($existing.State -eq 'Running') { throw 'Stop the existing task and verify port 8502 is free before converting it.' }
$launcher = Join-Path $RepoPath 'deploy\launch_team.ps1'
if (-not (Test-Path $launcher)) { throw 'Team launcher not found.' }
$backup = Join-Path $RepoPath ('.cache\AutoBOM-Team-Host-before-boot-{0}.xml' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $backup) | Out-Null
Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath $backup -Encoding Unicode
$credential = Get-Credential -UserName $UserName -Message 'Windows account password for unattended AutoBOM (not Windows Hello PIN)'
if (-not $credential) { throw 'No credential supplied; existing task unchanged.' }
$arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -RepoPath "{1}"' -f $launcher,$RepoPath.TrimEnd('\')
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments -WorkingDirectory $RepoPath
$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.Delay = 'PT30S'
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -User $credential.UserName -Password $credential.GetNetworkCredential().Password -RunLevel Limited -Force -Description 'AutoBOM loopback backend behind YankInternalToolsCaddy; starts before login.' | Out-Null
Write-Host "Task configured but NOT started. Previous task XML: $backup"
Write-Host "Start manually after the Caddy upstream is ready: Start-ScheduledTask -TaskName '$taskName'"
