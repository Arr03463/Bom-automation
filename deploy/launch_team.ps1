param([string]$RepoPath = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = "Stop"
$RepoPath = $RepoPath.TrimEnd('\')
Set-Location $RepoPath
$pythonExe = Join-Path $RepoPath '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) { throw 'AutoBOM virtual environment is missing.' }

# Caddy is the network-facing entry point. The backend is loopback-only.
$address = '127.0.0.1'
$env:STREAMLIT_SERVER_ADDRESS = $address
$env:STREAMLIT_SERVER_PORT = '8502'
$env:STREAMLIT_SERVER_HEADLESS = 'true'
$env:STREAMLIT_SERVER_ENABLE_CORS = 'true'
$env:STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION = 'true'

$dataRoot = Join-Path (Split-Path -Parent $RepoPath) 'AutoBOM-data'
$env:AUTOBOM_RUNS_ROOT = Join-Path $dataRoot 'runs'
$env:AUTOBOM_CACHE_ROOT = Join-Path $dataRoot 'cache'
$env:AUTOBOM_LOGS_DIR = Join-Path $dataRoot 'logs'
$env:DIGIKEY_TOKEN_STORE = 'file'
$env:DIGIKEY_TOKEN_STORE_PATH = Join-Path $dataRoot 'tokens'
New-Item -ItemType Directory -Force -Path $env:AUTOBOM_LOGS_DIR | Out-Null
$logFile = Join-Path $env:AUTOBOM_LOGS_DIR ("autobom-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))

# Each start gets its own log. Keep the latest 30 launch logs.
Get-ChildItem $env:AUTOBOM_LOGS_DIR -Filter 'autobom-*.log' |
    Sort-Object LastWriteTime -Descending | Select-Object -Skip 30 |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName }

Write-Host 'AutoBOM team address: https://autobom.tools.yanktech.net'
Write-Host "AutoBOM backend: http://${address}:8502"
Write-Host "Log: $logFile"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'launch_production.ps1') -RepoPath $RepoPath -ServerAddress '127.0.0.1' -ServerPort 8502 *> $logFile
exit $LASTEXITCODE
