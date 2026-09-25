# AutoBOM production launch script -- CORE LAUNCH MECHANISM, wrapper-independent.
#
# This script does the actual work of starting AutoBOM correctly: locate
# the checkout, activate the production virtualenv, load production
# environment variables, run the preflight check, copy the production
# Streamlit config into place, and launch Streamlit. It is deliberately
# NOT tied to any specific service wrapper (Windows Service via sc.exe,
# NSSM, Task Scheduler, etc.) -- whatever wrapper the team approves can
# simply invoke this script as its start command. See
# windows_service_install.ps1.template for a generic sc.exe example.
#
# This script does NOT install anything. Run it manually to verify
# AutoBOM starts correctly before wiring up any service wrapper.
#
# Usage -- production (explicit paths, e.g. from a service wrapper):
#   powershell -ExecutionPolicy Bypass -File launch_production.ps1 `
#       -RepoPath "C:\AutoBOM\prod\repo" `
#       -VenvPath "C:\AutoBOM\prod\.venv" `
#       -EnvFile "C:\AutoBOM\prod\repo\.env"
#
# Usage -- local/operator testing (no params needed): all three default
# to this checkout's own layout (repo root = this script's parent
# directory, .venv, .env), so the SAME script backs both
# Start_AutoBOM.bat/deploy\launch_local.ps1 and the production service
# install templates -- one launch mechanism, not two.
#   powershell -ExecutionPolicy Bypass -File launch_production.ps1

param(
    [string]$RepoPath = (Split-Path -Parent $PSScriptRoot),

    [string]$VenvPath = (Join-Path (Split-Path -Parent $PSScriptRoot) ".venv"),

    [string]$EnvFile = (Join-Path (Split-Path -Parent $PSScriptRoot) ".env")
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $RepoPath)) {
    Write-Error "Repo path does not exist: $RepoPath"
    exit 1
}
if (-not (Test-Path $EnvFile)) {
    Write-Error "Env file does not exist: $EnvFile"
    exit 1
}

Set-Location $RepoPath

$pythonExe = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Error "Python not found in virtualenv: $pythonExe (did you create/update the production venv?)"
    exit 1
}

# Load KEY=value pairs from the production env file into THIS process's
# environment (not the repo's .env -- that file must not exist in the
# production checkout; see Documentation/AutoBOM_Deployment_Guide.md).
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $key, $value = $line.Split("=", 2)
        [System.Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim(), "Process")
    }
}

# Production Streamlit config: copy into place if not already current.
# Comparing content (not just existence) so an updated template in the
# checkout is picked up on the next launch without a manual step.
$streamlitDir = Join-Path $RepoPath ".streamlit"
$targetConfig = Join-Path $streamlitDir "config.toml"
$sourceConfig = Join-Path $RepoPath "deploy\streamlit_config.prod.toml"
if (Test-Path $sourceConfig) {
    New-Item -ItemType Directory -Force -Path $streamlitDir | Out-Null
    $needsCopy = $true
    if (Test-Path $targetConfig) {
        $needsCopy = (Get-FileHash $sourceConfig).Hash -ne (Get-FileHash $targetConfig).Hash
    }
    if ($needsCopy) {
        Copy-Item $sourceConfig $targetConfig -Force
        Write-Host "Updated production Streamlit config."
    }
} else {
    Write-Warning "deploy\streamlit_config.prod.toml not found; Streamlit will use its own defaults."
}

# Preflight: never creates a vendor cart/MyList, never prints secrets.
# A FAIL here stops the launch before Streamlit even starts.
Write-Host "Running deployment preflight..."
& $pythonExe "src\deployment_preflight.py"
$preflightExitCode = $LASTEXITCODE
if ($preflightExitCode -ne 0) {
    Write-Error "Preflight reported FAIL (exit code $preflightExitCode). Not starting AutoBOM. Review the output above."
    exit $preflightExitCode
}

Write-Host "Preflight passed (or WARN-only). Starting AutoBOM..."

# The actual long-running process. Whatever wrapper invokes this script
# should treat THIS as the process to supervise/restart.
& $pythonExe -m streamlit run app.py
exit $LASTEXITCODE
