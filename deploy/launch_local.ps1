# AutoBOM one-click launcher -- for local/operator testing AND for
# manually starting AutoBOM on the actual deployment machine (e.g. before
# a formal Windows service is installed there, or an ad hoc restart).
#
# Thin wrapper around launch_production.ps1 -- reuses that script's
# existing env-loading/preflight/Streamlit-start logic verbatim instead
# of duplicating it (the SAME script a formal Task Scheduler/NSSM service
# install would invoke as its start command -- see
# windows_task_scheduler_install.ps1.template /
# windows_service_install_nssm.ps1.template). This file adds only what a
# double-clicked, human-at-the-keyboard launch specifically needs on top:
# start the app in the background, wait until it is actually responding,
# then open the browser -- a service supervisor doesn't want any of that.
#
# Invoked by Start_AutoBOM.bat at the repository root; not meant to be
# double-clicked directly (a .ps1 double-click typically just opens an
# editor rather than running it, depending on Windows file associations).
#
# IMPORTANT: starting AutoBOM here never creates a Mouser cart or DigiKey
# MyList and never regenerates purchasing artifacts -- those only happen
# from an explicit "Regenerate Purchasing" click inside the running app
# (see src/workflow_runner.py). Launching the app is not a BOM run.

param(
    [string]$RepoPath = (Split-Path -Parent $PSScriptRoot),
    [int]$Port = 8501,
    [int]$TimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"

function Fail($message) {
    Write-Host ""
    Write-Host "ERROR: $message" -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to close this window"
    exit 1
}

# A trailing backslash (e.g. from a batch file's %~dp0, which always
# ends in one) sits directly before the closing quote everywhere this
# script re-quotes a path into a child process's argument list below --
# Windows' command-line parser reads "\"" as an ESCAPED quote rather than
# end-of-argument, corrupting that and every following argument. Strip it
# here, once, rather than relying on every caller to remember not to pass
# a trailing backslash.
$RepoPath = $RepoPath.TrimEnd('\')

Write-Host "AutoBOM local launcher"
Write-Host "Repository: $RepoPath"

$venvPath = Join-Path $RepoPath ".venv"
$envFile = Join-Path $RepoPath ".env"
$launchScript = Join-Path $PSScriptRoot "launch_production.ps1"

if (-not (Test-Path $launchScript)) {
    Fail "Launch script not found: $launchScript (repository checkout looks incomplete)."
}
if (-not (Test-Path $envFile)) {
    Fail "No .env found at $envFile`nCopy .env.example to .env in the repository root and fill in your configuration, then try again."
}
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    Fail (
        "Python virtual environment not found at $venvPath`n" +
        "Create it first (from the repository root):`n" +
        "  py -3 -m venv .venv`n" +
        "  .\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt"
    )
}

# Force local, browser-friendly settings without touching the repo's
# .env: headless so Streamlit itself does NOT also try to open a browser
# (this script opens it, only after confirming the server actually
# responds) -- and the configured port/address, explicitly, so this
# always matches the URL this script polls and opens below.
$env:STREAMLIT_SERVER_HEADLESS = "true"
$env:STREAMLIT_SERVER_PORT = "$Port"
$env:STREAMLIT_SERVER_ADDRESS = "127.0.0.1"

Write-Host "Starting AutoBOM -- this window shows startup errors, keep it open..."
Write-Host ""

$process = Start-Process -FilePath "powershell.exe" `
    -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$launchScript`"",
        "-RepoPath", "`"$RepoPath`"", "-VenvPath", "`"$venvPath`"", "-EnvFile", "`"$envFile`""
    ) `
    -NoNewWindow -PassThru

$url = "http://127.0.0.1:$Port"
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$ready = $false

Write-Host "Waiting for AutoBOM to respond at $url ..."
while ((Get-Date) -lt $deadline) {
    if ($process.HasExited) {
        Fail "AutoBOM exited during startup (exit code $($process.ExitCode)). Review the messages above (a preflight failure or missing configuration is the most likely cause)."
    }

    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
        # Not up yet -- this is expected while Streamlit is still
        # starting; keep polling rather than treating it as failure.
    }

    Start-Sleep -Seconds 1
}

if (-not $ready) {
    Fail "AutoBOM did not respond at $url within $TimeoutSeconds seconds."
}

Write-Host "AutoBOM is up. Opening your browser..."
Start-Process $url

Write-Host ""
Write-Host "AutoBOM is running in this window. Close this window (or press Ctrl+C) to stop AutoBOM."
Wait-Process -Id $process.Id
